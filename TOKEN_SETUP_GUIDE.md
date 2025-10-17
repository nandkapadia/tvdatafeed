# TradingView Token Setup Guide

## 🎯 Quick Start

Run the interactive helper script:

```bash
python3 token_helper.py
```

This script will:
- ✅ Check if you have a cached token
- ✅ Validate if your token is still working
- ✅ Guide you through token extraction if needed
- ✅ Test your authentication

---

## 📋 What You'll Need

1. **TradingView Account** (free or paid)
2. **Web Browser** (Chrome, Firefox, Edge, or Safari)
3. **5 minutes** to follow the guided process

---

## 🚀 Three Ways to Get Started

### **Option 1: Interactive Helper** (Recommended - Easiest!)

```bash
cd /Users/nandkapadia/tvdatafeed
python3 token_helper.py
```

The script will walk you through everything step-by-step!

---

### **Option 2: Manual Token Extraction**

If you prefer to do it manually:

1. **Open TradingView login page** in your browser
2. **Open DevTools** (Press F12 or Ctrl+Shift+I / Cmd+Option+I on Mac)
3. **Go to Network tab** in DevTools
4. **Keep DevTools open** and login to TradingView
5. **Find the `signin` request** in the Network list
6. **Click it** → **Response tab**
7. **Look for:** `{"user":{"auth_token":"xxxxxxxxx"...}}`
8. **Copy the `auth_token` value**
9. **Save it to file:**

```bash
echo '{"token": "YOUR_TOKEN_HERE"}' > ~/.tv_token.json
```

---

### **Option 3: Use Anonymous Access** (No Token Needed)

If you don't need real-time data:

```python
from tvDatafeed import TvDatafeed

# No username/password = anonymous access (10-min delayed data)
tv = TvDatafeed()
data = tv.get_hist("AAPL", "NASDAQ", n_bars=100)
```

---

## 🔍 Understanding the Token

### **What is the auth_token?**
- A JWT (JSON Web Token) used to authenticate API requests
- Looks like: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` (200+ characters)
- Required for WebSocket/API communication with TradingView
- Different from the browser's `sessionid` cookie

### **Where is it stored?**
- **After extraction:** `~/.tv_token.json`
- **Format:** `{"token": "your_token_here"}`
- **Automatically used** by TvDatafeed when available

### **How long does it last?**
- Typically valid for several months
- Automatically validated on each use
- You'll be prompted to refresh if it expires

---

## 🛠️ Troubleshooting

### **Problem: "Token validation failed"**

**Solution:**
```bash
# Delete the old token
rm ~/.tv_token.json

# Run the helper script again
python3 token_helper.py
```

---

### **Problem: "Cannot find signin request in Network tab"**

**Reasons:**
1. DevTools was opened AFTER login (open it BEFORE!)
2. Looking in wrong tab (use "Network", not "Console")
3. Network tab was cleared (refresh page and try again)

**Solution:**
1. Logout of TradingView
2. Open DevTools **FIRST** (F12)
3. Go to Network tab
4. **Then** login again
5. Watch for the `signin` request to appear

---

### **Problem: "Token seems too short"**

**Reason:** You might have copied only part of the token

**Solution:**
- The token is VERY long (200+ characters)
- Make sure you copied the ENTIRE value
- It should start with `eyJ...` and have many more characters after
- Triple-click the value in DevTools to select all

---

### **Problem: "Data fetch returned empty result"**

**Possible causes:**
1. Token is valid but symbol/exchange is wrong
2. Network connectivity issue
3. TradingView API is down (rare)

**Solution:**
```python
# Test with a known-good symbol
from tvDatafeed import TvDatafeed
tv = TvDatafeed()
data = tv.get_hist("AAPL", "NASDAQ", n_bars=5)
print(data)
```

---

## 📚 Examples

### **Example 1: First Time Setup**

```bash
$ python3 token_helper.py

==================================================================
  TradingView Token Helper
==================================================================

This script will help you:
  ✓ Check if you have a cached authentication token
  ✓ Validate if your token is still working
  ✓ Extract a new token if needed
  ✓ Test your authentication

Let's get started!

==================================================================
  STEP 1: Checking for Cached Token
==================================================================
❌ No token cache found at: /Users/nandkapadia/.tv_token.json
   You'll need to extract a token from TradingView.

==================================================================
  STEP 2: Token Extraction Guide
==================================================================
[... follows interactive guide ...]
```

---

### **Example 2: Existing Token Check**

```bash
$ python3 token_helper.py

==================================================================
  STEP 1: Checking for Cached Token
==================================================================
✅ Token cache found at: /Users/nandkapadia/.tv_token.json
📄 Token loaded (length: 234 characters)
   Preview: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

------------------------------------------------------------------
  Validating Token
------------------------------------------------------------------
✅ Token is valid and working!

🎉 Great news! Your cached token is valid and working.

Would you like to test data fetching? (y/n): y
```

---

### **Example 3: Using TvDatafeed After Setup**

```python
from tvDatafeed import TvDatafeed, Interval

# Initialize (uses cached token automatically)
tv = TvDatafeed(username='your_username', password='your_password')

# Fetch historical data
data = tv.get_hist(
    symbol='AAPL',
    exchange='NASDAQ',
    interval=Interval.in_1_hour,
    n_bars=100
)

print(data.head())
```

---

## 🔐 Security Notes

### **Is my token secure?**

**Stored locally:**
- Token is saved to `~/.tv_token.json` on your machine
- Only you can access it (standard Unix file permissions)
- Not transmitted anywhere except to TradingView's API

**Best practices:**
- ✅ Don't commit `~/.tv_token.json` to git
- ✅ Don't share your token with others
- ✅ Regenerate token if you suspect it's compromised
- ✅ Use environment variables if deploying to servers

**To regenerate:**
```bash
rm ~/.tv_token.json
python3 token_helper.py
```

---

## 🎓 Understanding Token vs Session

### **Two Authentication Types:**

| Feature | sessionid (Browser) | auth_token (API) |
|---------|-------------------|------------------|
| **Purpose** | Web UI navigation | API/WebSocket calls |
| **Storage** | Browser cookies | Response body only |
| **Duration** | Session-based | Long-lived (months) |
| **Can extract?** | ✅ Yes (browser_cookie3) | ❌ No (must capture during login) |
| **Works for API?** | ❌ No | ✅ Yes |

**This is why we need Network tab extraction!**

---

## 💡 Tips & Tricks

### **Tip 1: Use Incognito/Private Mode**
```
Start fresh without existing sessions:
1. Open incognito/private browser window
2. Open DevTools
3. Login and extract token
4. No interference from existing cookies
```

### **Tip 2: Filter Network Requests**
```
In Network tab filter box, type: signin
This shows only relevant requests
```

### **Tip 3: Check Token Anytime**
```bash
# Quick token check
cat ~/.tv_token.json

# Quick validation
python3 -c "
from pathlib import Path
import json
data = json.loads(Path('~/.tv_token.json').expanduser().read_text())
print(f\"Token: {data['token'][:40]}...\")
print(f\"Length: {len(data['token'])} characters\")
"
```

### **Tip 4: Backup Your Token**
```bash
# Backup
cp ~/.tv_token.json ~/.tv_token.backup.json

# Restore
cp ~/.tv_token.backup.json ~/.tv_token.json
```

---

## 📞 Need Help?

1. **Run the helper script:** `python3 token_helper.py`
2. **Check this guide:** Read through troubleshooting section
3. **Test anonymous access:** Verify basic functionality works
4. **Check logs:** Enable debug logging in your code

---

## ✅ Success Checklist

After running the helper script, you should have:

- [ ] Token file created at `~/.tv_token.json`
- [ ] Token validated successfully
- [ ] Test data fetch completed
- [ ] TvDatafeed working normally

**You're all set!** 🎉

---

## 📖 Additional Resources

- **Main README:** `/Users/nandkapadia/tvdatafeed/README.md`
- **CLAUDE.md:** Developer documentation
- **Example Scripts:** See `examples/` directory
- **Token Helper:** `token_helper.py` (this interactive script)
