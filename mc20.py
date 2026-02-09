#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Scheduler for CLAW Minting
Includes:
1. Violent Minting Swarm (Attack Mode)
2. Automated Recovery (Index-Agent API)
3. Rate Limit Management
"""

import requests
import json
import threading
import time
import random
import string
from pathlib import Path
from datetime import datetime

# --- Configuration ---
BASE_DIR = Path(__file__).parent.absolute()
AGENTS_FILE = BASE_DIR / "copy.json"
THREADS_PER_AGENT = 1  # Safe mode: Single request per agent
BASE_URL = "https://www.moltbook.com/api/v1"

def register_agent(agent_name):
    """Register a new agent and return the API key + print claim instructions"""
    url = f"{BASE_URL}/agents/register"
    payload = {
        "name": agent_name,
        "description": f"AI Agent {agent_name} for CLAW minting"
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code in (200, 201):
            data = r.json()
            agent_data = data.get("agent", {})
            api_key = agent_data.get("api_key")
            claim_url = agent_data.get("claim_url")          # 关键：claim 链接
            verification_code = agent_data.get("verification_code")

            print(f"✅ Registered {agent_name}!")
            print(f"   API Key: {api_key}")
            if verification_code:
                print(f"   🔐 Verification Code: {verification_code}")
            if claim_url:
                print(f"   ⚠️ CLAIM URL (必须手动访问激活！): {claim_url}")
                print("\n   【激活步骤 - 必须手动完成】")
                print("   1. 打开上面的 CLAIM URL")
                print("   2. 页面会显示验证要求，通常需要你在 X (Twitter) 上发一条包含 verification_code 的帖子")
                print("   3. 发帖示例：'Verifying my Moltbook agent: {verification_code} @moltbook'")
                print("   4. 把发出的 X 帖子链接复制回 claim 页面提交")
                print("   5. 验证通过后 agent 才能正常发帖！（通常几分钟到几小时生效）")
                print("   注意：不完成 claim，API key 无效，无法 mint！")
            else:
                print("   ⚠️ 没有返回 claim_url，可能已激活或平台变更。请检查响应：")
                print(r.text)
            print("\n   IMPORTANT: 保存好 API key！丢失无法找回。")
            return api_key
        else:
            print(f"❌ Registration failed for {agent_name} (HTTP {r.status_code}): {r.text[:300]}")
            if "name already taken" in r.text.lower():
                print("   → 建议改名，比如加随机后缀：{agent_name}_{random.randint(1000,9999)}")
            elif "rate limit" in r.text.lower():
                print("   → 平台限流，稍等几分钟或换 IP 再试")
            return None
    except Exception as e:
        print(f"❌ Error registering {agent_name}: {e}")
        return None
INDEXER_URL = "https://mbc20.xyz/api"
SUBMOLT = "mbc-20"

def log(agent_name, message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{agent_name}] {message}", flush=True)

def generate_nonce(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def recovery_loop(agents):
    """
    Background thread that periodically tells mbc20.xyz to index our agents.
    This handles the "Missing a mint?" functionality automatically.
    """
    log("RECOVERY", "Starting Indexer Recovery Loop (Every 5 mins)...")
    
    while True:
        for agent in agents:
            name = agent.get("name")
            try:
                # Call the specific API endpoint we discovered
                r = requests.get(f"{INDEXER_URL}/index-agent?name={name}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        indexed = data.get("indexed", 0)
                        total = data.get("totalPosts", 0)
                        log("RECOVERY", f"[{name}] Sync OK. Total: {total}, New Indexed: {indexed}")
                    else:
                        log("RECOVERY", f"[{name}] Sync Failed: {data}")
                else:
                    log("RECOVERY", f"[{name}] HTTP {r.status_code}")
            except Exception as e:
                log("RECOVERY", f"[{name}] Error: {e}")
            
            # Small delay between agents to be nice
            time.sleep(10)
        
        # Wait 5 minutes before next full cycle
        time.sleep(300)

def run_agent_loop(agent_config):
    name = agent_config.get("name")
    api_key = agent_config.get("api_key")
    
    agent_barrier = threading.Barrier(THREADS_PER_AGENT)
    req_results = []
    results_lock = threading.Lock()

    def attack_thread(worker_id):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        nonce = generate_nonce()
        
        # MINT MODE ONLY
        mint_content = f'{{"p":"mbc-20","op":"mint","tick":"CLAW","amt":"100"}}'
        
        # Add random fluff to avoid duplicate content detection
        fluff_options = [
            "Exploring the CLAW ecosystem today! ",
            "Another step in decentralized minting: ",
            f"Agent update #{random.randint(1,999)}: ",
            "Reflecting on token utility... ",
            "To the moon with mbc20! ",
            "Claw is the law! ",
            "Building on Moltbook... "
        ]
        random_fluff = random.choice(fluff_options)
        
        final_content = f'{mint_content} {random_fluff} mbc20.xyz {nonce}'
        title_prefix = "Mint CLAW"

        payload = {
            "title": f"{title_prefix} {nonce}",
            "content": final_content,
            "submolt": SUBMOLT, 
            "is_draft": False
        }

        try:
            agent_barrier.wait()
        except threading.BrokenBarrierError:
            return

        try:
            r = requests.post(f"{BASE_URL}/posts", headers=headers, json=payload)
            log(name, f"Response: {r.status_code} {r.text[:200]}") # Debug print
            with results_lock:
                req_results.append((r.status_code, r.json()))
        except Exception as e:
            log(name, f"Request Exception: {e}")
            pass

    # MAIN LOOP
    # Mint Only Mode
    
    while True:
        req_results = []
        log(name, f"Preparing single MINT request...")
        
        workers = []
        for i in range(THREADS_PER_AGENT):
            t = threading.Thread(target=attack_thread, args=(i,))
            workers.append(t)
            t.start()
            
        for t in workers:
            t.join()

        success_count = 0
        retry_minutes = 2 * 60 
        got_429 = False

        for status, data in req_results:
            if (status == 200 or status == 201) and (data.get("success") or data.get("post")):
                success_count += 1
                log(name, f"[SUCCESS] Post ID: {data.get('post', {}).get('id')}")
                    
            elif status == 429:
                got_429 = True
                r_min = data.get("retry_after_minutes")
                if r_min:
                    retry_minutes = r_min
        
        if success_count > 0:
            log(name, f"Attack Successful! {success_count} mints landed.")
            sleep_time = (2 * 60 * 60) + random.randint(60, 300)
            log(name, f"Sleeping for 2 hours (Success)...")
        elif got_429:
            # Check for specific retry advice
            retry_seconds = 0
            # Look for retry_after_seconds first (more precise)
            for _, data in req_results:
                if data.get("retry_after_seconds"):
                    retry_seconds = data.get("retry_after_seconds")
                    break
            
            if retry_seconds > 0:
                sleep_time = retry_seconds + 5 # Add 5s buffer
                log(name, f"Rate Limited. Server says wait {retry_seconds}s.")
            else:
                # Fallback to minutes if seconds not found
                sleep_time = (retry_minutes * 60) + 30 
                log(name, f"Rate Limited. Wait {retry_minutes} mins.")
                
            log(name, f"Sleeping for {sleep_time:.0f} seconds...")
        else:
            sleep_time = 60
            log(name, "Unknown error. Retrying in 60s...")

        time.sleep(sleep_time)

def main():
    if not AGENTS_FILE.exists():
        print(f"[ERROR] {AGENTS_FILE} not found!")
        # Create template if not exists
        with open(AGENTS_FILE, "w", encoding="utf-8") as f:
            json.dump([{"name": "YourAgentName", "api_key": ""}], f, indent=4)
        print(f"Created template {AGENTS_FILE}. Please edit it.")
        return

    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        agents = json.load(f)

    # Registration Phase
    updated = False
    valid_agents = []
    
    print(f"[INFO] Checking {len(agents)} agents for registration...")
    
    for agent in agents:
        name = agent.get("name")
        api_key = agent.get("api_key")
        
        # Skip placeholder defaults
        if name == "name" or name == "YourAgentName":
            print(f"⚠️  Skipping placeholder agent '{name}'. Please edit {AGENTS_FILE}.")
            continue

        # If no valid key (or placeholder 'key'), try to register
        if not api_key or api_key == "key" or len(api_key) < 10:
            print(f"🆕 Registering new agent: {name}...")
            new_key = register_agent(name)
            if new_key:
                agent["api_key"] = new_key
                updated = True
                valid_agents.append(agent)
                print(f"\n[提示] {agent['name']} 已注册，但需手动完成 claim 激活！")
                print("   脚本会继续运行，但未激活的 agent 发帖会失败（401 Unauthorized 或类似）")
                # More detailed advice
                print(f"   请尽快完成上面打印的 claim 步骤。\n")
        else:
            valid_agents.append(agent)

    # Save updated keys back to file
    if updated:
        with open(AGENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(agents, f, indent=4)
        print(f"💾 Updated {AGENTS_FILE} with new API keys.")

    if not valid_agents:
        print("❌ No valid agents found to run. Exiting.")
        return

    print(f"[INFO] Starting Smart Scheduler with {len(valid_agents)} agents...")
    print("-" * 50)

    # Start Recovery Thread
    recovery_t = threading.Thread(target=recovery_loop, args=(valid_agents,))
    recovery_t.daemon = True
    recovery_t.start()

    # Start Agent Loops
    for agent in valid_agents:
        t = threading.Thread(target=run_agent_loop, args=(agent,))
        t.daemon = True
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Stopping...")

if __name__ == "__main__":
    main()
    