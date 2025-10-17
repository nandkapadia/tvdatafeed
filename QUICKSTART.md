# 🚀 Quick Start Guide

## ⚡ Get Started in 2 Minutes

### **Step 1: Run the Helper Script**

```bash
cd /Users/nandkapadia/tvdatafeed
python3 token_helper.py
```

### **Step 2: Follow the Interactive Guide**

The script will:
1. ✅ Check if you already have a token
2. ✅ Open your browser to TradingView login
3. ✅ Show you exactly where to find the token
4. ✅ Validate and save your token
5. ✅ Test that everything works

### **Step 3: Use TvDatafeed**

```python
from tvDatafeed import TvDatafeed, Interval

# Uses your cached token automatically
tv = TvDatafeed(username='your_username', password='your_password')

# Get historical data
data = tv.get_hist('AAPL', 'NASDAQ', Interval.in_1_hour, n_bars=100)
print(data)
```

---

## 🎯 Three Use Cases

### **Case 1: I Just Want It to Work** (Easiest)

```python
from tvDatafeed import TvDatafeed

# Anonymous access - no token needed, data is 10-min delayed
tv = TvDatafeed()
data = tv.get_hist('AAPL', 'NASDAQ', n_bars=100)
```

**Pros:** Zero setup, works immediately
**Cons:** 10-minute data delay

---

### **Case 2: I Need Real-Time Data** (One-Time Setup)

**Setup (once):**
```bash
python3 token_helper.py
# Follow the guide to extract your token (takes 5 min)
```

**Use (every time):**
```python
from tvDatafeed import TvDatafeed

tv = TvDatafeed(username='user', password='pass')  # Uses cached token
data = tv.get_hist('AAPL', 'NASDAQ', n_bars=100)
```

**Pros:** Real-time data, automatic after setup
**Cons:** 5-minute initial setup

---

### **Case 3: I'm a Developer** (Maximum Control)

```python
from tvDatafeed import TvDatafeed, Interval

# Custom token cache location
tv = TvDatafeed(
    username='user',
    password='pass',
    token_cache_file='/custom/path/token.json'
)

# Advanced usage
data = tv.get_hist(
    symbol='AAPL',
    exchange='NASDAQ',
    interval=Interval.in_5_minute,
    n_bars=500,
    extended_session=True  # Include pre/post market
)
```

---

## 🔧 Common Commands

### **Check Token Status**
```bash
python3 token_helper.py
```

### **Remove Old Token**
```bash
rm ~/.tv_token.json
```

### **Test Connection**
```python
from tvDatafeed import TvDatafeed
tv = TvDatafeed()
print(tv.get_hist('AAPL', 'NASDAQ', n_bars=5))
```

---

## 📚 More Information

- **Detailed Setup:** See [TOKEN_SETUP_GUIDE.md](TOKEN_SETUP_GUIDE.md)
- **Full Documentation:** See [README.md](README.md)
- **Developer Docs:** See [CLAUDE.md](CLAUDE.md)

---

## ❓ FAQ

**Q: Do I need a TradingView account?**
A: No, anonymous access works without an account (10-min delayed data)

**Q: How long does the token last?**
A: Typically months. The library validates it automatically.

**Q: What if I get CAPTCHA?**
A: The helper script guides you through extracting the token manually (one-time)

**Q: Is my token secure?**
A: Yes, stored locally in `~/.tv_token.json`, only you can access it

**Q: Can I use this in production?**
A: Yes! Token caching makes it production-ready

---

## 🎉 You're Ready!

Choose your path:
- 🏃 **Quick & Easy:** Use anonymous access
- ⚡ **Real-Time Data:** Run `token_helper.py` now
- 📖 **Learn More:** Read the full guides

**Start coding:**
```python
from tvDatafeed import TvDatafeed
tv = TvDatafeed()
print(tv.get_hist('AAPL', 'NASDAQ', n_bars=10))
```
