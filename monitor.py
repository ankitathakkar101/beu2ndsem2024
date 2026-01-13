import asyncio
import os
import time
import aiohttp
import zipfile
import urllib.parse
from io import BytesIO
from typing import Optional, Tuple
from playwright.async_api import async_playwright

# --- CONFIGURATION ---

# Ensure this is set in your environment variables or replace with the actual URL string for testing
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") 

EXAM_CONFIG = {
    "ordinal_sem": "1st",
    "roman_sem": "I",
    "session": "2024",
    "held_month": "May",
    "held_year": "2025"
}

REG_LIST = [
    "24101148001", "24101148003", "24101148004", "24101148005", "24101148006",
    "24101148007", "24101148009", "24101148010", "24101148011", "24101148013",
    "24101148014", "24101148015", "24101148016", "24101148018", "24101148019",
    "24101148020", "24101148021", "24101148022", "24101148023", "24101148024",
    "24101148025", "24101148026", "24101148027", "24101148029", "24101148030",
    "24101148031", "24101148032", "24101148033", "24101148034", "24101148035",
    "24101148036", "24101148038", "24101148039", "24101148040", "24101148041",
    "24101148042", "24101148044", "24101148045", "24101148046", "24101148047",
    "24101148048", "24101148049", "24101148050", "24101148052", "24101148053",
    "24101148054", "24101148055", "24101148056", "24101148057", "24101148058",
    "24101148059", "24101148060", "24102148001", "24102148002", "24102148003",
    "24102148004", "24102148006", "24102148008", "24102148009", "24102148010",
    "24102148011", "24102148012", "24102148013", "24102148014", "24102148017",
    "24102148018", "24102148019", "24102148020", "24102148021", "24102148022",
    "24102148023", "24102148024", "24102148025", "24102148026", "24102148027",
    "24102148028", "24103148001", "24103148002", "24103148003", "24103148004",
    "24103148005", "24103148006", "24103148007", "24103148008", "24103148009",
    "24103148010", "24103148012", "24103148013", "24103148014", "24103148015",
    "24103148016", "24103148018", "24103148020", "24103148021", "24103148022",
    "24103148023", "24103148024", "24103148025", "24103148028", "24103148030",
    "24104148001", "24104148002", "24104148003", "24104148004", "24104148005",
    "24104148006", "24104148007", "24104148008", "24104148009", "24104148010",
    "24104148011", "24104148012", "24104148013", "24104148014", "24104148015",
    "24104148016", "24104148017", "24104148018", "24104148019", "24104148020",
    "24104148021", "24104148022", "24104148023", "24104148025", "24104148026",
    "24104148027", "24104148028", "24104148029", "24104148030", "24104148032",
    "24152148001", "24152148002", "24152148003", "24152148004", "24152148005",
    "24152148006", "24152148007", "24152148008", "24152148009", "24152148010",
    "24152148011", "24152148012", "24152148014", "24152148016", "24152148017",
    "24152148018", "24152148019", "24152148020", "24152148021", "24152148022",
    "24152148023", "24152148024", "24152148025", "24152148026", "24152148027",
    "24152148028", "24156148006", "24156148007", "24156148008", "24156148010",
    "24156148011", "24156148012", "24156148013", "24156148014", "24156148015",
    "24156148017", "24156148018", "24156148019", "24156148020", "24156148021",
    "24156148022", "24156148023", "24156148024", "24156148025", "24156148026",
    "24156148027", "24156148028", "24156148029", "24156148030", "24156148031",
    "24156148032", "24156148034", "24156148036", "24156148038", "24156148039",
    "24156148040", "24156148041", "24156148042", "24156148043", "24156148044",
    "24156148045", "24156148046", "24156148047", "24156148048", "24156148049",
    "24156148050"
]

# --- RESTORED USER SETTINGS ---
CHECK_INTERVAL = 5          # Check every 5 seconds (Fast loop)
CONTINUOUS_DURATION = 900   # Run for 15 minutes max
CONCURRENCY_LIMIT = 6       # 6 Browsers
SCHEDULED_INTERVAL = 600    # "I am alive" hourly message
DOWN_REMINDER_DELAY = 600   # Remind every 10 mins if down

class DiscordMonitor:
    def __init__(self):
        self.last_status: Optional[str] = None
        self.last_scheduled_time: float = 0
        self.last_down_alert_time: float = 0
        self.rate_limit_remaining = 5
        self.rate_limit_reset = 0

    # --- RATE LIMITED DISCORD MESSENGER ---
    async def send_discord_message(self, content: str) -> bool:
        if not DISCORD_WEBHOOK_URL: return False
        
        now = time.time()
        # Wait if rate limited
        if self.rate_limit_remaining <= 0 and now < self.rate_limit_reset:
            await asyncio.sleep(self.rate_limit_reset - now)
            
        payload = {"content": content, "username": "BEU Monitor"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                    # Update rate limit headers
                    self.rate_limit_remaining = int(resp.headers.get("X-RateLimit-Remaining", 5))
                    reset_after = resp.headers.get("X-RateLimit-Reset-After")
                    if reset_after: self.rate_limit_reset = now + float(reset_after)
                    
                    if resp.status == 429: # Too Many Requests
                        retry = float(resp.headers.get("retry-after", 1))
                        await asyncio.sleep(retry)
                        return await self.send_discord_message(content)
                    return resp.status in (200, 204)
        except:
            return False

    async def send_file(self, filename: str, data: BytesIO) -> bool:
        if not DISCORD_WEBHOOK_URL: return False
        form = aiohttp.FormData()
        data.seek(0)
        form.add_field("file", data, filename=filename, content_type="application/zip")
        form.add_field("username", "BEU Monitor")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(DISCORD_WEBHOOK_URL, data=form, timeout=600) as resp:
                    if resp.status == 429:
                        retry = float(resp.headers.get("retry-after", 1))
                        await asyncio.sleep(retry)
                        return await self.send_file(filename, data)
                    return resp.status in (200, 204)
        except:
            return False

    # --- SITE LOGIC ---
    def construct_url(self, reg_no):
        params = {
            'name': f"B.Tech. {EXAM_CONFIG['ordinal_sem']} Semester Examination, {EXAM_CONFIG['session']}",
            'semester': EXAM_CONFIG['roman_sem'],
            'session': EXAM_CONFIG['session'],
            'regNo': str(reg_no),
            'exam_held': f"{EXAM_CONFIG['held_month']}/{EXAM_CONFIG['held_year']}"
        }
        return f"https://beu-bih.ac.in/result-three?{urllib.parse.urlencode(params)}"

    async def check_connection(self) -> str:
        """
        FIXED: Checks if the site is UP by verifying the RegNo exists in the page text.
        This prevents false positives on maintenance pages.
        """
        test_reg = REG_LIST[0] 
        canary_url = self.construct_url(test_reg)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(canary_url, timeout=10) as resp:
                    if resp.status == 200:
                        html_content = await resp.text()
                        
                        # CRITICAL FIX: 
                        # Only return "UP" if the Registration No is actually found in the HTML.
                        if str(test_reg) in html_content:
                            return "UP"
                        
                    return "DOWN"
        except Exception as e:
            return "DOWN"

    async def fetch_student_pdf(self, context, reg_no, semaphore) -> Tuple[str, Optional[bytes]]:
        """Worker to fetch a single PDF with improved waiting logic"""
        async with semaphore:
            page = await context.new_page()
            try:
                await page.goto(self.construct_url(reg_no), timeout=40000)
                
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass 
                
                # Gatekeeper: Wait for RegNo to appear in the text (Validates content loaded)
                await page.wait_for_selector(f"text={reg_no}", timeout=15000)

                pdf = await page.pdf(format="A4", print_background=True)
                await page.close()
                return (reg_no, pdf)
            except Exception as e:
                print(f"Failed {reg_no}: {e}")
                await page.close()
                return (reg_no, None)

    async def parallel_download_zip(self) -> BytesIO:
        """Manages the parallel download"""
        buffer = BytesIO()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
            
            tasks = [self.fetch_student_pdf(context, reg, sem) for reg in REG_LIST]
            results = await asyncio.gather(*tasks)
            
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                count = 0
                for reg, pdf in results:
                    if pdf:
                        zf.writestr(f"Result_{reg}.pdf", pdf)
                        count += 1
                    else:
                        zf.writestr(f"MISSING_{reg}.txt", "Failed to download.")
            
            await browser.close()
            print(f"Downloaded {count} results successfully.")
        
        buffer.seek(0)
        return buffer

    async def continuous_status(self, end_time):
        """The 'Spam' loop: sends UP status continuously"""
        print("Entering Continuous Status Loop...")
        while time.time() < end_time:
            left = int(end_time - time.time())
            if left <= 0: break
            
            # Send message every CHECK_INTERVAL (5s)
            await self.send_discord_message(f"✅ Website still UP ({left}s left)")
            await asyncio.sleep(CHECK_INTERVAL)

    # --- MAIN LOOP ---
    async def run(self):
        print(f"Monitor Started. Run Duration: {CONTINUOUS_DURATION}s")
        await self.send_discord_message("🔍 **Monitor Started** (Checking every 5s)")
        
        start_time = time.time()
        end_time = start_time + CONTINUOUS_DURATION
        
        while time.time() < end_time:
            # 1. Check Status
            status = await self.check_connection()
            now = time.time()

            # 2. Status Changed Logic
            if status == "UP":
                # If it WAS down (or first check), triggering Immediate Action
                if self.last_status != "UP":
                    await self.send_discord_message("🚨 **SITE IS LIVE!** Starting Download...")
                    
                    # A. Download
                    zip_data = await self.parallel_download_zip()
                    zip_size = zip_data.getbuffer().nbytes / (1024*1024)
                    
                    # B. Upload
                    await self.send_discord_message(f"📤 ZIP Generated ({zip_size:.2f} MB). Uploading...")
                    success = await self.send_file(f"Results_{int(now)}.zip", zip_data)
                    
                    if success:
                        await self.send_discord_message("✅ **Bulk Download Complete & Uploaded**")
                    else:
                        await self.send_discord_message("❌ Upload Failed (Check file size limits).")

                    # C. Enter the 'Spam' Loop (Continuous Status)
                    # This loop runs until time is up, then the script exits
                    await self.continuous_status(end_time)
                    return # Exit after continuous loop finishes

            elif status == "DOWN":
                # Handle Notifications
                if self.last_status == "UP":
                    await self.send_discord_message("🔴 Website went **DOWN**")
                    self.last_down_alert_time = now
                elif self.last_status is None:
                    # First check is DOWN
                    await self.send_discord_message("🔴 Website is currently **DOWN**")
                    self.last_down_alert_time = now
                elif (now - self.last_down_alert_time) > DOWN_REMINDER_DELAY:
                    # Reminder every 10 mins
                    await self.send_discord_message("🔴 Reminder: Website is still **DOWN**")
                    self.last_down_alert_time = now
            
            self.last_status = status
            
            # 3. Wait for next check
            await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(DiscordMonitor().run())
