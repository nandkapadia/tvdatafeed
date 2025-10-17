#!/usr/bin/env python3
"""
TradingView Token Helper
========================
Interactive script to help manage your TradingView authentication token.

Features:
- Check if you have a cached token
- Validate if your token is still working
- Guide you through manual token extraction when needed
- Test your authentication after setup
"""

import json
import logging
import sys
import webbrowser
from pathlib import Path

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

# Constants
TOKEN_FILE = Path("~/.tv_token.json").expanduser()
TRADINGVIEW_LOGIN = "https://www.tradingview.com/accounts/signin/"
VALIDATION_URL = "https://www.tradingview.com/accounts/current/"


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_section(text):
    """Print a formatted section."""
    print("\n" + "-" * 70)
    print(f"  {text}")
    print("-" * 70)


def check_token_exists():
    """Check if token cache file exists."""
    print_header("STEP 1: Checking for Cached Token")

    if TOKEN_FILE.exists():
        print(f"✅ Token cache found at: {TOKEN_FILE}")
        return True
    else:
        print(f"❌ No token cache found at: {TOKEN_FILE}")
        print("   You'll need to extract a token from TradingView.")
        return False


def validate_token(token):
    """Validate if a token is still working by attempting a data fetch."""
    print_section("Validating Token")

    print("🔄 Testing token with actual data fetch...", end="", flush=True)

    try:
        from tvDatafeed import TvDatafeed, Interval

        # Create instance and try to fetch a small amount of data
        tv = TvDatafeed()
        data = tv.get_hist("AAPL", "NASDAQ", interval=Interval.in_daily, n_bars=1)

        print(" Done!")

        if data is not None and len(data) > 0:
            print("✅ Token is valid and working!")
            return True
        else:
            print("❌ Token validation failed - no data returned")
            print("   The token may be expired or invalid.")
            return False

    except Exception as e:
        print(" Error!")
        print(f"⚠️  Error validating token: {e}")
        print("   The token may be expired or invalid.")
        return False


def load_cached_token():
    """Load token from cache file."""
    try:
        data = json.loads(TOKEN_FILE.read_text())
        token = data.get("token")

        if not token:
            print("❌ Token file exists but is empty or invalid")
            return None

        print(f"📄 Token loaded (length: {len(token)} characters)")
        print(f"   Preview: {token[:40]}...")

        return token

    except Exception as e:
        print(f"❌ Error reading token file: {e}")
        return None


def save_token(token):
    """Save token to cache file."""
    try:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps({"token": token}))
        print(f"✅ Token saved to: {TOKEN_FILE}")
        return True
    except Exception as e:
        print(f"❌ Error saving token: {e}")
        return False


def show_extraction_guide():
    """Show detailed guide for extracting token from Network tab."""
    print_header("STEP 2: Token Extraction Guide")

    print("""
⚠️  IMPORTANT: The auth_token is ONLY visible during the login process!
   You need to capture it from the Network tab as it happens.

📋 DETAILED INSTRUCTIONS:
""")

    print("""
1️⃣  PREPARE YOUR BROWSER:
   • Open a new browser window/tab
   • Press F12 (or Ctrl+Shift+I on Mac: Cmd+Option+I)
   • Click the "Network" tab in DevTools
   • IMPORTANT: Keep DevTools open during the entire process!

2️⃣  FILTER NETWORK REQUESTS (Optional but helpful):
   • In the Network tab, look for a filter/search box
   • Type: signin
   • This will help you find the right request

3️⃣  LOGIN PROCESS:
   • I'll open TradingView login page in 5 seconds...
   • Complete the CAPTCHA (if shown)
   • Enter your username and password
   • Click "Sign in"
   • KEEP WATCHING THE NETWORK TAB!

4️⃣  FIND THE AUTH TOKEN:
   • After you click "Sign in", watch the Network tab
   • Look for a request named "signin" or "signin/"
   • Click on it
   • Click the "Preview" or "Response" tab
   • You should see JSON that looks like:
     {
       "user": {
         "username": "your_username",
         "auth_token": "eyJhbGc...",    ← This is what you need!
         ...
       }
     }

5️⃣  COPY THE TOKEN:
   • Find the "auth_token" field
   • Copy the ENTIRE value (it's very long, usually 200+ characters)
   • It should look like: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   • Come back here and paste it

6️⃣  WHAT IF I DON'T SEE IT?:
   • Make sure DevTools was open BEFORE you clicked "Sign in"
   • Try logging out and logging in again (with DevTools open)
   • Check both "Preview" and "Response" tabs
   • Look for any request with "signin" in the name
""")

    input("\n📌 Press Enter when you're ready to proceed...")

    print("\n🌐 Opening TradingView login page in 5 seconds...")
    print("   Get ready to watch the Network tab!")

    import time
    for i in range(5, 0, -1):
        print(f"   {i}...")
        time.sleep(1)

    try:
        webbrowser.open(TRADINGVIEW_LOGIN)
        print("\n✅ Browser opened!")
    except Exception as e:
        print(f"\n⚠️  Could not open browser automatically: {e}")
        print(f"   Please open this URL manually: {TRADINGVIEW_LOGIN}")


def prompt_for_token():
    """Prompt user to enter token manually."""
    print_section("Enter Your Token")

    print("""
Paste the auth_token value here (the very long string).
Tips:
  • It should be 100+ characters long
  • It should start with something like: eyJhbGc...
  • Press Ctrl+V (Cmd+V on Mac) to paste
  • Press Enter when done
""")

    while True:
        try:
            token = input("auth_token: ").strip()

            if not token:
                print("❌ No token entered. Try again or press Ctrl+C to cancel.")
                continue

            # Basic validation
            if len(token) < 50:
                print(f"⚠️  Token seems too short ({len(token)} characters)")
                retry = input("   Continue anyway? (y/n): ").strip().lower()
                if retry != 'y':
                    continue

            if not token.replace("-", "").replace("_", "").replace(".", "").isalnum():
                print("⚠️  Token contains unexpected characters")
                retry = input("   Continue anyway? (y/n): ").strip().lower()
                if retry != 'y':
                    continue

            return token

        except KeyboardInterrupt:
            print("\n\n❌ Cancelled by user")
            return None
        except EOFError:
            print("\n\n❌ Input cancelled")
            return None


def test_authentication():
    """Test if authentication works with the token."""
    print_header("STEP 3: Testing Authentication")

    try:
        from tvDatafeed import TvDatafeed, Interval

        print("📡 Creating TvDatafeed instance...")
        tv = TvDatafeed()  # Will use cached token

        print("📊 Testing data fetch (AAPL, 5 bars)...")
        data = tv.get_hist("AAPL", "NASDAQ", interval=Interval.in_daily, n_bars=5)

        if data is not None and len(data) > 0:
            print("\n✅ SUCCESS! Authentication is working!")
            print(f"\n📈 Sample data (latest 3 bars):")
            print(data.head(3).to_string())
            return True
        else:
            print("\n⚠️  Data fetch returned empty result")
            print("   This might indicate an issue with the token or symbol")
            return False

    except Exception as e:
        print(f"\n❌ Error testing authentication: {e}")
        return False


def main():
    """Main interactive flow."""
    print_header("TradingView Token Helper")

    print("""
This script will help you:
  ✓ Check if you have a cached authentication token
  ✓ Validate if your token is still working
  ✓ Extract a new token if needed
  ✓ Test your authentication

Let's get started!
""")

    # Step 1: Check for existing token
    has_token = check_token_exists()

    if has_token:
        # Load and validate existing token
        token = load_cached_token()

        if token:
            if validate_token(token):
                print("\n🎉 Great news! Your cached token is valid and working.")

                choice = input("\nWould you like to test data fetching? (y/n): ").strip().lower()
                if choice == 'y':
                    test_authentication()

                print("\n✅ All done! You can now use TvDatafeed normally.")
                return 0
            else:
                print("\n⚠️  Your cached token is invalid or expired.")
                choice = input("Would you like to extract a new token? (y/n): ").strip().lower()
                if choice != 'y':
                    print("\n❌ Exiting. Run this script again when you're ready.")
                    return 1
                # Continue to extraction
        else:
            print("\n⚠️  Could not load token from cache.")
            choice = input("Would you like to extract a new token? (y/n): ").strip().lower()
            if choice != 'y':
                print("\n❌ Exiting. Run this script again when you're ready.")
                return 1

    # Step 2: Guide user through extraction
    show_extraction_guide()

    print("\n" + "=" * 70)
    print("  After you've logged in and found the token...")
    print("=" * 70)

    token = prompt_for_token()

    if not token:
        print("\n❌ No token provided. Exiting.")
        return 1

    # Validate the new token
    if not validate_token(token):
        print("\n⚠️  Warning: Token validation failed!")
        choice = input("Save it anyway? (y/n): ").strip().lower()
        if choice != 'y':
            print("\n❌ Token not saved. Exiting.")
            return 1

    # Save the token
    if save_token(token):
        print("\n🎉 Success! Token has been saved.")

        choice = input("\nWould you like to test data fetching? (y/n): ").strip().lower()
        if choice == 'y':
            test_authentication()

        print("\n✅ All done! You can now use TvDatafeed normally:")
        print("\n    from tvDatafeed import TvDatafeed")
        print("    tv = TvDatafeed(username='your_username', password='your_password')")
        print("    data = tv.get_hist('AAPL', 'NASDAQ', n_bars=100)")

        return 0
    else:
        print("\n❌ Failed to save token. Please try again.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user. Exiting.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
