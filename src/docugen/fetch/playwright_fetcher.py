from .base import Fetcher, FetchResult
import anyio

class PlaywrightFetcher(Fetcher):
    async def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise Exception("Playwright is not installed. Please run 'pip install playwright'.")
            
        try:
            async with async_playwright() as pw:
                browser = None
                context = None
                try:
                    try:
                        browser = await pw.chromium.launch()
                    except Exception as e:
                        if "playwright install" in str(e).lower():
                            raise Exception("Playwright browsers not installed. Please run 'playwright install chromium'.")
                        raise e
                    
                    context = await browser.new_context()
                    page = await context.new_page()
                    
                    # Store WASM binaries found during navigation
                    wasm_binaries = {}

                    async def intercept_route(route):
                        try:
                            try:
                                # response = await route.fetch()
                                # Using fetch() might be hanging if the resource is huge or the server is slow
                                # Let's only continue if it's not a WASM file we want to intercept
                                if ".wasm" in route.request.url.split('?')[0]:
                                    response = await route.fetch()
                                    body = await response.body()
                                    # Store with absolute URL
                                    wasm_binaries[route.request.url] = body
                                    
                                    # If the server returned wrong MIME type, fix it for the browser
                                    headers = response.headers.copy()
                                    if "application/wasm" not in headers.get("content-type", "").lower():
                                        headers["content-type"] = "application/wasm"
                                        try:
                                            await route.fulfill(
                                                response=response,
                                                headers=headers,
                                                body=body
                                            )
                                            return
                                        except Exception:
                                            pass
                                else:
                                    await route.continue_()
                                    return
                            except Exception:
                                # Page or context might have closed
                                try:
                                    await route.continue_()
                                except:
                                    pass
                                return
                        except Exception:
                            pass

                    await page.route("**/*", intercept_route)

                    try:
                        # Using a shorter timeout for navigation that might be a download
                        await page.goto(url, wait_until="networkidle", timeout=30000)
                    except Exception as e:
                        if "Download is starting" in str(e):
                            return FetchResult(url, f"<html><body>Download started for {url}</body></html>")
                        raise e
                    
                    # Wait for any JS to finish rendering content
                    await page.wait_for_timeout(5000)

                    # For SPA sites like Three.js, ensure the hash change actually loads content
                    # and if there are examples, wait for them to load.
                    if "#" in url:
                        # Sometimes we need to force a re-navigation or wait longer for hash routes
                        await page.wait_for_load_state("networkidle")
                        await page.wait_for_timeout(2000)

                    # Try to expand any common "optional" sidebars or TOCs
                    await page.evaluate("""
                        () => {
                            const patterns = [
                                /table of contents/i,
                                /on this page/i,
                                /menu/i,
                                /expand/i,
                                /sidebar/i
                            ];
                            const buttons = Array.from(document.querySelectorAll('button, a, .button, [role="button"]'));
                            for (const btn of buttons) {
                                const text = (btn.innerText || btn.title || btn.ariaLabel || "").trim();
                                if (patterns.some(p => p.test(text))) {
                                    // Check if it's likely collapsed (common patterns)
                                    const isCollapsed = 
                                        btn.getAttribute('aria-expanded') === 'false' || 
                                        btn.classList.contains('collapsed') ||
                                        btn.classList.contains('closed');
                                    
                                    if (isCollapsed) {
                                        try {
                                            btn.click();
                                            console.log("Clicked to expand: " + text);
                                        } catch (e) {}
                                    }
                                }
                            }
                        }
                    """)
                    
                    # Wait a bit after potential expansion
                    await page.wait_for_timeout(1000)
                    
                    # Scroll from top to bottom to trigger lazy-loading content
                    await page.evaluate("""
                        async () => {
                            await new Promise((resolve) => {
                                let totalHeight = 0;
                                let distance = 100;
                                let timer = setInterval(() => {
                                    let scrollHeight = document.body.scrollHeight;
                                    window.scrollBy(0, distance);
                                    totalHeight += distance;

                                    if(totalHeight >= scrollHeight || totalHeight > 10000){ // Cap scrolling
                                        clearInterval(timer);
                                        resolve();
                                    }
                                }, 100);
                            });
                            window.scrollTo(0, 0);
                        }
                    """)

                    # Try to extract content from iframes and inject it into the main page.
                    # Many documentation sites use iframes for the main content (e.g. Three.js).
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        
                        # Heuristic: skip very small iframes (likely ads, trackers, or widgets)
                        # or iframes without a name/id unless they look like content
                        try:
                            frame_name = frame.name.lower()
                        except:
                            frame_name = ""
                            
                        if not frame_name and frame.frame_element:
                            try:
                                frame_name = (await frame.frame_element.get_attribute("id") or "").lower()
                            except:
                                pass

                        # Common names for content iframes
                        content_names = ["viewer", "content", "main", "frame", "article"]
                        is_likely_content = any(name in frame_name for name in content_names)
                        
                        if is_likely_content or not frame_name:
                            try:
                                # Wait for some content to be present in the iframe
                                try:
                                    async with anyio.fail_after(5):
                                        await frame.wait_for_load_state("networkidle", timeout=5000)
                                except Exception:
                                    pass
                                
                                try:
                                    async with anyio.fail_after(5):
                                        iframe_content = await frame.content()
                                except Exception:
                                    continue
                                
                                # Inject iframe body into the main page so it's crawlable/indexable
                                await page.evaluate("""
                                    (content, frameId) => {
                                        const id = 'iframe-content-injected-' + frameId;
                                        if (!document.getElementById(id)) {
                                            const div = document.createElement('div');
                                            div.id = id;
                                            div.style.display = 'none';
                                            div.innerHTML = content;
                                            document.body.appendChild(div);
                                        }
                                    }
                                """, iframe_content, frame_name or "unnamed")
                            except:
                                pass

                    # Wait for stability: check if the content size remains constant
                    last_html_len = 0
                    stable_count = 0
                    max_stability_checks = 15
                    for i in range(max_stability_checks):
                        try:
                            # Use a simpler/faster way to check stability if content() is slow
                            current_len = await page.evaluate("() => document.documentElement.outerHTML.length")
                            
                            if current_len > 0 and current_len == last_html_len:
                                stable_count += 1
                            else:
                                stable_count = 0
                                last_html_len = current_len
                            
                            if stable_count >= 3:
                                break
                        except Exception:
                            break
                        
                        await page.wait_for_timeout(1000)
                    
                    html = await page.content()

                    # Embed collected WASM binaries into the HTML
                    if wasm_binaries:
                        import base64
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, "lxml")
                        
                        if not soup.body:
                            # Fallback if no body
                            body_tag = soup.new_tag("body")
                            soup.append(body_tag)
                        
                        # Add a script for each WASM
                        for wasm_url, wasm_body in wasm_binaries.items():
                            wasm_b64 = base64.b64encode(wasm_body).decode('utf-8')
                            wasm_script = soup.new_tag("script")
                            wasm_script["type"] = "application/wasm-embedded"
                            wasm_script["data-wasm-url"] = wasm_url
                            wasm_script.string = wasm_b64
                            soup.body.append(wasm_script)
                        
                        # Add the shim script
                        shim_script = soup.new_tag("script")
                        shim_script.string = """
                        (function() {
                            const originalFetch = window.fetch;
                            window.fetch = async function(url, options) {
                                const urlString = url.toString();
                                const absoluteUrl = new URL(urlString, window.location.href).href;
                                
                                // Try exact match first, then try matching by filename
                                let embedded = document.querySelector(`script[type="application/wasm-embedded"][data-wasm-url="${absoluteUrl}"]`);
                                
                                if (!embedded) {
                                    const filename = urlString.split('/').pop().split('?')[0];
                                    embedded = Array.from(document.querySelectorAll('script[type="application/wasm-embedded"]'))
                                        .find(s => {
                                            const storedUrl = s.getAttribute('data-wasm-url');
                                            return storedUrl.split('/').pop().split('?')[0] === filename;
                                        });
                                }

                                if (embedded) {
                                    const binaryString = atob(embedded.textContent);
                                    const bytes = new Uint8Array(binaryString.length);
                                    for (let i = 0; i < binaryString.length; i++) {
                                        bytes[i] = binaryString.charCodeAt(i);
                                    }
                                    return new Response(bytes, {
                                        status: 200,
                                        statusText: 'OK',
                                        headers: { 'Content-Type': 'application/wasm' }
                                    });
                                }
                                return originalFetch(url, options);
                            };

                            // Also shim instantiateStreaming
                            const originalInstantiateStreaming = WebAssembly.instantiateStreaming;
                            WebAssembly.instantiateStreaming = async function(source, importObject) {
                                try {
                                    return await originalInstantiateStreaming(source, importObject);
                                } catch (e) {
                                    if (source instanceof Promise || source instanceof Response) {
                                        const response = (source instanceof Promise) ? await source : source;
                                        const buffer = await response.arrayBuffer();
                                        return WebAssembly.instantiate(buffer, importObject);
                                    }
                                    throw e;
                                }
                            };
                        })();
                        """
                        # Insert shim at the beginning of head or body
                        if soup.head:
                            soup.head.insert(0, shim_script)
                        else:
                            soup.body.insert(0, shim_script)
                        
                        html = str(soup)

                    return FetchResult(page.url, html)
                finally:
                    if context:
                        try:
                            # Unroute all to stop any pending interceptors
                            await page.unroute("**/*")
                            await context.close()
                        except:
                            pass
                    if browser:
                        await browser.close()
        except Exception as e:
            raise Exception(f"Playwright error: {e}")
