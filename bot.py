import os
import uuid
import json
import time
import urllib.request
import urllib.parse
import re
import threading
from dotenv import load_dotenv
from git import Repo
from keep_alive import start_server
# Load environment variables
load_dotenv()
start_server()

class TelegramRedirectBot:
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN")
        self.git_repo_url = os.getenv("GIT_REPO_URL")
        self.github_username = os.getenv("GITHUB_USERNAME")
        self.github_email = os.getenv("GITHUB_EMAIL")
        
        # Extract repo name from URL
        if self.git_repo_url:
            self.repo_name = self.git_repo_url.split('/')[-1].replace('.git', '')
        else:
            self.repo_name = "redirect_repo"
            
        self.repo_path = self.repo_name
        self.github_pages_base = f"https://{self.github_username}.github.io/{self.repo_name}/"
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.offset = 0
        
    def validate_config(self):
        """Validate all required configuration"""
        if not self.bot_token:
            print("❌ BOT_TOKEN not found in environment variables")
            return False
        if not self.github_username:
            print("❌ GITHUB_USERNAME not found in environment variables")
            return False
        if not self.git_repo_url:
            print("❌ GIT_REPO_URL not found in environment variables")
            return False
        return True
    
    def sanitize_url(self, url):
        """Parse and sanitize the input URL"""
        try:
            # Remove whitespace
            url = url.strip()
            
            # Add protocol if missing
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Parse URL to validate
            parsed = urllib.parse.urlparse(url)
            
            # Basic validation
            if not parsed.netloc:
                return None, "Invalid URL: No domain found"
            
            # Reconstruct clean URL
            clean_url = urllib.parse.urlunparse(parsed)
            
            # Security check - block potentially dangerous URLs
            dangerous_patterns = [
                r'javascript:',
                r'data:',
                r'file:',
                r'ftp:',
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, clean_url, re.IGNORECASE):
                    return None, "Invalid URL: Potentially unsafe protocol"
            
            return clean_url, None
            
        except Exception as e:
            return None, f"URL parsing error: {str(e)}"
    
    def create_redirect_page(self, original_url, folder_name):
        """Create folder and minimal HTML redirect file"""
        try:
            full_path = os.path.join(self.repo_path, folder_name)
            print(f"📁 Creating folder at: {full_path}")
            os.makedirs(full_path, exist_ok=True)

            html_content = f'''<!DOCTYPE html>
    <html>
    <head>
    <meta http-equiv="refresh" content="0; URL={original_url}" />
    <title></title>
    <style>
    body {{
    display: none;
    }}
    </style>
    </head>
    <body></body>
    </html>'''

            html_file_path = os.path.join(full_path, "index.html")
            print(f"📝 Writing index.html to: {html_file_path}")
            with open(html_file_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Confirm it's actually written
            if os.path.exists(html_file_path):
                print("✅ index.html created successfully.")
            else:
                print("❌ index.html was not created.")

            return True, None

        except Exception as e:
            print(f"❌ Failed to create redirect page: {e}")
            return False, f"Failed to create redirect page: {str(e)}"

    
    def push_to_github(self, original_url, folder_name):
        """Push changes to GitHub repository with conflict handling"""
        try:
            # Clean start if repo exists but has issues
            if os.path.exists(self.repo_path):
                try:
                    repo = Repo(self.repo_path)
                    # Test if repo is accessible
                    repo.git.status()
                except Exception:
                    # If repo is corrupted, delete and re-clone
                    import shutil
                    shutil.rmtree(self.repo_path)
            
            # Initialize/open repository
            if not os.path.exists(self.repo_path):
                repo = Repo.clone_from(self.git_repo_url, self.repo_path)
            else:
                repo = Repo(self.repo_path)
            
            # Configure git user
            config = repo.config_writer()
            config.set_value("user", "name", self.github_username)
            if self.github_email:
                config.set_value("user", "email", self.github_email)
            else:
                config.set_value("user", "email", f"{self.github_username}@users.noreply.github.com")
            config.release()
            
            # Pull latest changes first
            try:
                origin = repo.remote(name='origin')
                origin.pull()
            except Exception as pull_error:
                print(f"⚠️ Pull warning: {pull_error}")
            
            # Add files
            repo.git.add(A=True)
            
            # Check if there are changes to commit
            if repo.is_dirty():
                # Commit changes with generic message
                commit_message = f"Update {folder_name}"
                repo.index.commit(commit_message)
                
                # Push to GitHub
                origin.push()
                
                return True, None
            else:
                return True, "No changes to commit"
                
        except Exception as e:
            return False, f"GitHub push failed: {str(e)}"
    
    def check_url_live(self, url, max_attempts=12, delay=5):
        """Check if URL is live by making HTTP requests"""
        for attempt in range(max_attempts):
            try:
                req = urllib.request.Request(url, method='HEAD')
                req.add_header('User-Agent', 'Mozilla/5.0 (compatible; Bot)')
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.getcode() == 200:
                        return True, attempt + 1
            except Exception:
                pass
            
            if attempt < max_attempts - 1:
                time.sleep(delay)
        
        return False, max_attempts
    
    def send_message(self, chat_id, text, parse_mode=None):
        """Send message to Telegram chat"""
        url = f"{self.api_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        
        try:
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
            req = urllib.request.Request(url, data=encoded_data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"Error sending message: {e}")
            return None
    
    def edit_message(self, chat_id, message_id, text, parse_mode=None):
        """Edit an existing message"""
        url = f"{self.api_url}/editMessageText"
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        
        try:
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
            req = urllib.request.Request(url, data=encoded_data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"Error editing message: {e}")
            return None
    
    def deployment_status_checker(self, chat_id, message_id, redirect_url, original_url, folder_name):
        """Background thread to check deployment status and update message"""
        deployment_msg = f"""🔄 *Deploying your redirect...*

🔗 *Your Link:* `{redirect_url}`
📋 *Original URL:* `{original_url}`
🎯 *Folder:* `{folder_name}`

⏳ *Status:* Checking deployment... (this usually takes 30-60 seconds)"""
        
        # Update message with deployment status
        self.edit_message(chat_id, message_id, deployment_msg, "Markdown")
        
        # Check if URL is live
        is_live, attempts = self.check_url_live(redirect_url)
        
        if is_live:
            success_msg = f"""✅ *Redirect is LIVE!*

🔗 *Your Link:*
`{redirect_url}`

📋 *Original URL:*
`{original_url}`

🎯 *Folder:* `{folder_name}`
⏱️ *Deployed in:* ~{attempts * 5} seconds

Your link is ready to use! 🚀"""
        else:
            success_msg = f"""⚠️ *Redirect Created (Deployment Pending)*

🔗 *Your Link:*
`{redirect_url}`

📋 *Original URL:*
`{original_url}`

🎯 *Folder:* `{folder_name}`

*Note:* GitHub Pages is still deploying. Your link should be active within a few minutes. Please try again shortly if it doesn't work immediately."""
        
        self.edit_message(chat_id, message_id, success_msg, "Markdown")
    
    def get_updates(self):
        """Get updates from Telegram"""
        url = f"{self.api_url}/getUpdates?offset={self.offset}&timeout=10"
        
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"Error getting updates: {e}")
            return None
    
    def handle_message(self, message):
        """Process incoming message"""
        try:
            chat_id = message['chat']['id']
            user_text = message.get('text', '').strip()
            user_name = message.get('from', {}).get('first_name', 'User')
            
            print(f"📨 Message from {user_name}: {user_text}")
            
            # Handle start command
            if user_text.startswith('/start'):
                welcome_msg = """🚀 *URL Redirect Bot*
                
Send me any URL and I'll create a short redirect link for you!

📝 *How to use:*
• Send any URL (with or without http://)
• Get back a GitHub Pages redirect link
• I'll check when it's live and notify you!
• Share your new link anywhere!

*Example:*
Send: `google.com`
Get: `https://you.github.io/loader/x1/`

*New:* Real-time deployment status updates! 🔄"""
                
                self.send_message(chat_id, welcome_msg, "Markdown")
                return
            
            # Handle help command
            if user_text.startswith('/help'):
                help_msg = """ℹ️ *Help*

*Supported formats:*
• `google.com`
• `https://example.com`
• `http://site.com/path`

*Features:*
• Automatic HTTPS upgrade
• URL validation & sanitization
• Fast GitHub Pages hosting
• Real-time deployment tracking
• Unlimited redirects

*Process:*
1. Send URL → Bot creates redirect
2. Bot pushes to GitHub
3. Bot monitors deployment status
4. You get notified when live! ✅

Just send any URL to get started! 🎯"""
                
                self.send_message(chat_id, help_msg, "Markdown")
                return
            
            # Parse & Sanitize URL
            clean_url, error = self.sanitize_url(user_text)
            
            if error:
                self.send_message(chat_id, f"❌ {error}")
                return
            
            # Send initial processing message
            processing_msg = f"""🔄 *Processing your URL...*

📋 *URL:* `{clean_url}`

⏳ *Step 1:* Creating redirect page...
⏳ *Step 2:* Pushing to GitHub...
⏳ *Step 3:* Will monitor deployment status..."""
            
            response = self.send_message(chat_id, processing_msg, "Markdown")
            
            if not response or not response.get('ok'):
                self.send_message(chat_id, "❌ Failed to send status message")
                return
            
            message_id = response['result']['message_id']
            
            # Generate unique folder name
            folder_name = str(uuid.uuid4())[:8]
            
            # Create folder + index.html
            success, error = self.create_redirect_page(clean_url, folder_name)
            
            if not success:
                error_msg = f"❌ *Failed to create redirect*\n\n*Error:* {error}"
                self.edit_message(chat_id, message_id, error_msg, "Markdown")
                return
            
            # Update message
            pushing_msg = f"""🔄 *Processing your URL...*

📋 *URL:* `{clean_url}`

✅ *Step 1:* Redirect page created
⏳ *Step 2:* Pushing to GitHub...
⏳ *Step 3:* Will monitor deployment status..."""
            
            self.edit_message(chat_id, message_id, pushing_msg, "Markdown")
            
            # Push to GitHub
            success, error = self.push_to_github(clean_url, folder_name)
            
            if not success:
                error_msg = f"❌ *Failed to push to GitHub*\n\n*Error:* {error}"
                self.edit_message(chat_id, message_id, error_msg, "Markdown")
                return
            
            # Generate redirect URL
            redirect_url = f"{self.github_pages_base}{folder_name}/"
            
            # Start background deployment checker
            checker_thread = threading.Thread(
                target=self.deployment_status_checker,
                args=(chat_id, message_id, redirect_url, clean_url, folder_name),
                daemon=True
            )
            checker_thread.start()
            
            print(f"✅ Redirect created! Monitoring deployment: {redirect_url}")
            
        except Exception as e:
            print(f"❌ Error handling message: {e}")
            chat_id = message.get('chat', {}).get('id')
            if chat_id:
                self.send_message(chat_id, f"❌ An unexpected error occurred: {str(e)}")
    
    def run(self):
        """Main bot loop"""
        print("🚀 Starting Telegram Redirect Bot...")
        
        # Validate configuration
        if not self.validate_config():
            return
        
        # Test bot connection
        try:
            url = f"{self.api_url}/getMe"
            with urllib.request.urlopen(url) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get('ok'):
                    bot_info = result.get('result', {})
                    print(f"✅ Bot connected: @{bot_info.get('username', 'Unknown')}")
                else:
                    print(f"❌ Bot connection failed: {result}")
                    return
        except Exception as e:
            print(f"❌ Bot connection error: {e}")
            print("💡 Try visiting: https://api.telegram.org/bot<TOKEN>/deleteWebhook")
            return
        
        print("🤖 Bot is running with deployment monitoring... Send /start to begin")
        print("Press Ctrl+C to stop")
        
        # Main polling loop
        while True:
            try:
                updates = self.get_updates()
                
                if updates and updates.get('ok'):
                    for update in updates.get('result', []):
                        self.offset = update['update_id'] + 1
                        
                        if 'message' in update:
                            self.handle_message(update['message'])
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                print("\n🛑 Bot stopped by user")
                break
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                time.sleep(5)

def main():
    """Entry point"""
    bot = TelegramRedirectBot()
    bot.run()

if __name__ == '__main__':
    main()
