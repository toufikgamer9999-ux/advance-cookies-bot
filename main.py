# Source: Sayed's Code
import telebot, instaloader, time, os, pyotp, threading, sys, requests, base64, uuid, re
from telebot import types, apihelper
from concurrent.futures import ThreadPoolExecutor
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request

# মিডলওয়্যার চালু রাখা হচ্ছে
apihelper.ENABLE_MIDDLEWARE = True

# ================= [ টোকন ইনপুট নেওয়া ] =================
def get_bot_token():
    if len(sys.argv) > 1:
        return sys.argv[1]  # কমান্ড লাইন থেকে টোকন নেওয়া
    else:
        print("🔑 আপনার বোট টোকন দিন:")
        token = input("➜ ").strip()
        if not token:
            print("❌ টোকন দেওয়া বাধ্যতামূলক!")
            sys.exit(1)
        return token

# টোকন সেট করা
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ================= [ বোট চালু ] =================
try:
    bot = telebot.TeleBot(BOT_TOKEN)
    print(f"✅ বোট সফলভাবে চালু হয়েছে!")
    print(f"📡 বট টেস্ট করা হচ্ছে...")
    bot.get_me()  # টোকন ভ্যালিড কিনা চেক করা
    print(f"✅ টোকন ভ্যালিড!")
except Exception as e:
    print(f"❌ টোকন ইনভ্যালিড বা বোট চালু হয়নি: {e}")
    sys.exit(1)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
user_sessions = {}

# প্রগ্রেস বার কন্ট্রোল করার গ্লোবাল লক ও টাইম ট্র্যাকার
progress_lock = threading.Lock()
last_update_time = {}

# ================= [ বাটন ও সিকিউরিটি ফিল্টার ] =================
def get_start_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🚀 START EXTRACTING"))
    return markup

def get_cancel_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ CANCEL"))
    return markup

# ================= [ লাইভ প্রগ্রেস বার ইঞ্জিন ] =================
def send_progress(chat_id, message_id, current, total):
    global last_update_time
    now = time.time()
    
    # টেলিগ্রাম রেট লিমিট এড়াতে ১.৫ সেকেন্ডের বাফার (শেষ অ্যাকাউন্টটি সবসময় আপডেট হবে)
    if current < total and chat_id in last_update_time and (now - last_update_time[chat_id]) < 1.5:
        return
        
    last_update_time[chat_id] = now
    
    # পারসেন্টেজ ও প্রগ্রেস বার ক্যালকুলেশন
    percentage = int((current / total) * 100) if total > 0 else 0
    block = int(percentage / 10)
    progress_bar = "██" * block + "░░" * (10 - block)
    
    status_text = f"""╔════════════════════════╗
║ 𖣠 𝐏𝐑𝐎𝐂𝐄𝐒𝐒𝐈𝐍𝐆 𝐃𝐀𝐓𝐀 :                       ║
╚════════════════════════╝
𝐋𝐢𝐯𝐞 **𝐏𝐫𝐨𝐠𝐫𝐞𝐬𝐬 :** 
[{progress_bar}]  `{percentage}%`
𒀭**𝐒𝐭𝐚𝐭𝐮𝐬 ❯❯** `{current}` / `{total}` Processed
───────────────────────
⚙️ `Engine Running In Background`..."""
    
    try:
        with progress_lock:
            bot.edit_message_text(status_text, chat_id, message_id, parse_mode="Markdown")
    except Exception:
        pass

# ================= [ লগইন ইঞ্জিন ] =================
def login_worker(chat_id, u, p, k):
    if chat_id not in user_sessions: return
    L = instaloader.Instaloader(quiet=True, max_connection_attempts=1)
    L.context._session.headers.update({'User-Agent': UA})
    try:
        L.login(u, p)
        save_success(chat_id, L, u, p)
    except:
        try:
            totp = pyotp.TOTP(k.replace(" ", ""))
            L.two_factor_login(totp.now())
            save_success(chat_id, L, u, p)
        except:
            if chat_id in user_sessions:
                # ❌ চ্যাটে মেসেজ পাঠানো বন্ধ
                # 🟢 ফেইলড লিস্টে ইউজারনেম জমা এবং কাউন্টার আপডেট করা হচ্ছে
                user_sessions[chat_id]['failed_list'].append(u)
                user_sessions[chat_id]['current_count'] += 1
                
                send_progress(
                    chat_id, 
                    user_sessions[chat_id]['active_msg_id'], 
                    user_sessions[chat_id]['current_count'], 
                    user_sessions[chat_id]['total_accounts']
                )

def save_success(chat_id, L, u, p):
    if chat_id in user_sessions:
        cookies = L.context._session.cookies.get_dict()
        ck_str = "; ".join([f"{key}={val}" for key, val in cookies.items()])
        user_sessions[chat_id]['results'].append(f"{u}|{p}|{ck_str}")
        
        # ❌ চ্যাটে মেসেজ পাঠানো বন্ধ
        # 🟢 সাকসেস কাউন্টার ও প্রgress বার আপডেট করা হচ্ছে
        user_sessions[chat_id]['current_count'] += 1
        
        send_progress(
            chat_id, 
            user_sessions[chat_id]['active_msg_id'], 
            user_sessions[chat_id]['current_count'], 
            user_sessions[chat_id]['total_accounts']
        )

# ================= [ প্রসেস হ্যান্ডলার ] =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_chat_action(message.chat.id, 'typing')
    
    import datetime
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    
    welcome_text = f"""╔════════════════════════╗
║    👾 𝗛𝗢𝗦𝗦𝗔𝗜𝗡 𝗖𝗢𝗢𝗞𝗜𝗘𝗦 𝗕𝗢𝗧 👾     ║
╚════════════════════════╝
•                    ── ⋆⋅𖤓⋅⋆ ──                    •
⚡ **𝐒𝐭𝐚𝐭𝐮𝐬:** ONLINE 🟢
🛡 **𝐌𝐨𝐨𝐝:** `DIRECT EXPRESS ACTIVE`
───────────────────────
👤 **𝐔𝐬𝐞𝐫:** `{message.from_user.first_name}`
🆔 **𝐈𝐃:** `{message.from_user.id}`
⏰ **𝐓𝐢𝐦𝐞:** `{current_time}`
───────────────────────
`নিচের অপশন থেকে আপনার কাজ শুরু করুন`:"""
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_start_markup())

@bot.message_handler(func=lambda m: m.text == "❌ CANCEL")
def cancel_work(message):
    user_sessions.pop(message.chat.id, None)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(message.chat.id, """╔════════════════════════╗
║🔴𝗧𝗔𝗦𝗞 𝗖𝗔𝗡𝗖𝗘𝗟𝗟𝗘𝗗 :                         ║
╚════════════════════════╝
🚫 Operation successfully cancelled.
🔄 Click below to start over.
… … …
… !""", reply_markup=get_start_markup())

@bot.message_handler(func=lambda m: m.text == "🚀 START EXTRACTING")
def step1(message):
    bot.send_chat_action(message.chat.id, 'typing')
    msg = bot.send_message(message.chat.id, """╔════════════════════════╗
║👥𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 𝗟𝗜𝗦𝗧: (One  per Line)  ║
╚════════════════════════╝
𝐅𝐨𝐫 𝐄𝐱𝐚𝐦𝐩𝐥𝐞 :
username.1
username.2
... !""", reply_markup=get_cancel_markup())
    bot.register_next_step_handler(msg, step2)

def step2(message):
    if message.text == "❌ CANCEL": return
    chat_id = message.chat.id
    usernames = [u.strip() for u in message.text.splitlines() if u.strip()]
    user_sessions[chat_id] = {'u_list': usernames, 'results': [], 'failed_list': [], 'current_count': 0}
    bot.send_chat_action(message.chat.id, 'typing')
    msg = bot.send_message(chat_id, """╔════════════════════════╗
║ 🔑 𝗖𝗢𝗠𝗠𝗢𝗡 𝗣𝗔𝗦𝗦𝗪𝗢𝗥𝗗:                ║
╚════════════════════════╝
Give me a password:""", reply_markup=get_cancel_markup())
    bot.register_next_step_handler(msg, step3)

def step3(message):
    if message.text == "❌ CANCEL": return
    chat_id = message.chat.id
    user_sessions[chat_id]['common_pass'] = message.text.strip()
    bot.send_chat_action(message.chat.id, 'typing')
    msg = bot.send_message(chat_id, """╔════════════════════════╗
║🔐𝟮𝗙𝗔 SECURITY 𝗞𝗘𝗬𝗦: One per line  ║
╚════════════════════════╝
𝐅𝐨𝐫 𝐄𝐱𝐚𝐦𝐩𝐥𝐞 :
2FA key.1
2FA key.2
...!""", reply_markup=get_cancel_markup())
    bot.register_next_step_handler(msg, final_step)

def final_step(message):
    if message.text == "❌ CANCEL": return
    chat_id = message.chat.id
    keys = [k.strip() for k in message.text.splitlines() if k.strip()]
    u_list = user_sessions[chat_id]['u_list']
    p = user_sessions[chat_id]['common_pass']
    
    if len(u_list) != len(keys):
        bot.send_chat_action(message.chat.id, 'typing')
        bot.send_message(chat_id, f"""╔════════════════════════╗
║ ⚠ 𝗗𝗔𝗧𝗔 𝗠𝗜𝗦𝗠𝗔𝗧𝗖𝗛 𝗘𝗥𝗥𝗢𝗥 :          ║
╚════════════════════════╝
❌ `The number of usernames and 2FA keys does not match`!
📊 𝐒𝐮𝐦𝐦𝐚𝐫𝐲 :
👤 𝐓𝐨𝐭𝐚𝐥 𝐔𝐬𝐞𝐫𝐧𝐚𝐦𝐞: `{len(u_list)}` টি
🔐 𝐓𝐨𝐭𝐚𝐥 𝟐𝐅𝐚 𝐊𝐞𝐲: `{len(keys)}` টি
💡 `Please balance the lists and try again`.""", parse_mode="Markdown", reply_markup=get_start_markup())
        return
    
    # সেশন ডেটাতে টোটাল অ্যাকাউন্ট সেভ করা
    user_sessions[chat_id]['total_accounts'] = len(u_list)
    
    bot.send_chat_action(message.chat.id, 'typing')
    # প্রথম ইনিশিয়াল প্রগ্রেস মেসেজ পাঠানো হচ্ছে
    prog_msg = bot.send_message(chat_id, "⏳ **𝐈𝐧𝐢𝐭𝐢𝐚𝐥𝐢𝐳𝐢𝐧𝐠 𝐄𝐱𝐭𝐫𝐚𝐜𝐭𝐢𝐨𝐧 𝐒𝐲𝐬𝐭𝐞𝐦...**", parse_mode="Markdown")
    user_sessions[chat_id]['active_msg_id'] = prog_msg.message_id
    
    def keep_typing():
        while chat_id in user_sessions:
            if user_sessions[chat_id].get('current_count', 0) >= len(u_list):
                break
            bot.send_chat_action(chat_id, 'typing')
            time.sleep(4)

    import threading
    threading.Thread(target=keep_typing, daemon=True).start()
    executor = ThreadPoolExecutor(max_workers=100)
    for i in range(len(u_list)):
        if chat_id in user_sessions:
            executor.submit(login_worker, chat_id, u_list[i], p, keys[i])
            time.sleep(0.1)
    
    def finalize():
        executor.shutdown(wait=True)
        if chat_id in user_sessions:
            res = user_sessions[chat_id]['results']
            failed_res = user_sessions[chat_id]['failed_list']
            
            # প্রগ্রেস বারটি ১০০% করে দেওয়া হচ্ছে ফাইনাল ডাউনলোডের আগে
            send_progress(chat_id, user_sessions[chat_id]['active_msg_id'], len(u_list), len(u_list))
            time.sleep(1)
            
            # 📄 ১. ফেইল হওয়া অ্যাকাউন্টগুলোর ফাইল সবার উপরে পাঠানো হচ্ছে
            if failed_res:
                fail_fname = f"Failed_ID_List_999.txt"
                with open(fail_fname, "w") as f: f.write("\n".join(failed_res))
                bot.send_chat_action(chat_id, 'upload_document')
                bot.send_document(chat_id, open(fail_fname, "rb"), caption=f"🚫𝗙𝗮𝗶𝗹𝗱 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲 𝗟𝗶𝘀𝘁!\n" + f" 𝐓𝐨𝐭𝐚𝐥 𝐅𝐚𝐢𝐥𝐝: {len(failed_res)}")
                try: os.remove(fail_fname)
                except: pass
            
            # 📄 ২. সফল কুকি ফাইল এবং এটার ক্যাপশনেই টাস্ক রিপোর্ট ও বাটন অ্যাড করা হচ্ছে
            if res:
                fname = f"Your_Cookies_File.txt"
                with open(fname, "w") as f: f.write("\n".join(res))
                
                # ইনলাইন সাবমিট বাটন তৈরি
                markup = InlineKeyboardMarkup()
                submit_button = InlineKeyboardButton(text="📤 𝗦𝗨𝗕𝗠𝗜𝗧 𝗡𝗢𝗪 ", url="http://skysysx.net/e/boss")
                markup.add(submit_button)
                
                # ফাইলের ক্যাপশনেই মূল মেসেজের ডিজাইন
                caption_text = f"""╔════════════════════════╗
║ 📊 𝗧𝗔𝗦𝗞 𝗥𝗘𝗣𝗢𝗥𝗧 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗       ║
╚════════════════════════╝
───────────────────────
🏁 **𝐒𝐮𝐜𝐞𝐬𝐬:** `{len(res)}`  ✅
❌ **𝐅𝐚𝐢𝐥𝐞𝐝:** `{len(failed_res)}`  🛑
───────────────────────
Your files are ready! Please submit it:"""
                
                bot.send_chat_action(chat_id, 'upload_document')
                with open(fname, "rb") as d:
                    bot.send_document(chat_id, d, caption=caption_text, parse_mode="Markdown", reply_markup=markup)
                    bot.send_chat_action(message.chat.id, 'typing')
                    bot.send_message(chat_id, """╔════════════════════════╗
║ ✅ 𝗧𝗔𝗦𝗞 𝗙𝗜𝗡𝗜𝗦𝗛𝗘𝗗                              ║
╚════════════════════════╝
• All processes are done.
• Tap the button below to start a new task.""", parse_mode="Markdown", reply_markup=get_start_markup())
                try: os.remove(fname)
                except: pass
            else:
                # যদি কোনো কুকি সফল না হয়, শুধু ফেইল মেসেজ বাটনসহ দেখাবে
                markup = InlineKeyboardMarkup()
#                submit_button = InlineKeyboardButton(text="📤 𝗦𝗨𝗕𝗠𝗜𝗧 𝗡𝗢𝗪 ", url="http://skysysx.net/e/boss")
#                markup.add(submit_button)
                
                caption_text = f"""╔════════════════════════╗
║ 📊 𝗧𝗔𝗦𝗞 𝗥𝗘𝗣𝗢𝗥𝗧 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗       ║
╚════════════════════════╝
───────────────────────
🏁 **𝐒𝐮𝐜𝐞𝐬𝐬:** `0`  ✅
❌ **𝐅𝐚𝐢𝐥𝐞𝐝:** `{len(failed_res)}`  🛑
───────────────────────
🚫`No! Cookies extracted. Please try again`!"""
                bot.send_chat_action(message.chat.id, 'typing')
                bot.send_message(chat_id, caption_text, parse_mode="Markdown", reply_markup=get_start_markup())
                
            user_sessions.pop(chat_id, None)

    threading.Thread(target=finalize).start()

app = Flask(__name__)

# আপনার সার্ভারের URL এখানে বসান (অবশ্যই https হতে হবে)
# উদাহরণ: https://my-bot-server.onrender.com
WEBHOOK_URL_BASE = os.environ.get("WEBHOOK_URL_BASE") 
WEBHOOK_URL_PATH = f"/{BOT_TOKEN}/"

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Forbidden', 403

if __name__ == "__main__":
    # পুরোনো পোলিং কনফিগারেশন মুছে নতুন করে ওয়েব হুক সেট করা
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
    
    # অ্যাপটি রান করা
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
