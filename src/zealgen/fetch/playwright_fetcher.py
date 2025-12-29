from .base import Fetcher, FetchResult


class PlaywrightFetcher(Fetcher):
    async def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise Exception("Playwright is not installed. Please run 'pip install playwright'.")
            
        try:
            async with async_playwright() as pw:
                try:
                    browser = await pw.chromium.launch()
                except Exception as e:
                    if "playwright install" in str(e).lower():
                        raise Exception("Playwright browsers not installed. Please run 'playwright install chromium'.")
                    raise e
                    
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle")
                
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

                                if(totalHeight >= scrollHeight){
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
                    frame_name = frame.name.lower()
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
                            await frame.wait_for_load_state("networkidle", timeout=2000)
                            iframe_content = await frame.content()
                            
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
                for _ in range(max_stability_checks):
                    html = await page.content()
                    
                    # Consider all frames for stability
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        try:
                            f_html = await frame.content()
                            html += f_html
                        except:
                            pass

                    current_len = len(html)
                    if current_len > 0 and current_len == last_html_len:
                        stable_count += 1
                    else:
                        stable_count = 0
                        last_html_len = current_len
                    
                    if stable_count >= 3:
                        break
                    await page.wait_for_timeout(1000)

                html = await page.content()
                final_url = page.url
                await browser.close()
                return FetchResult(final_url, html)
        except Exception as e:
            raise Exception(f"Playwright error: {e}")
