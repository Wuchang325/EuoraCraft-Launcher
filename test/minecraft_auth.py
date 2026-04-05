import webbrowser
import requests
import json
import time
import sys

CLIENT_ID = "f1709935-df0b-400c-843a-530a77fb8d3c"
SCOPE = "XboxLive.SignIn offline_access"

def device_code_login():
    """使用 Device Code Flow 获取微软 Token"""
    
    # 步骤1：获取 Device Code
    device_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
    data = {
        "client_id": CLIENT_ID,
        "scope": SCOPE
    }
    
    print("[1/5] 正在请求设备代码...")
    resp = requests.post(device_url, data=data)
    
    if resp.status_code != 200:
        raise Exception(f"获取设备代码失败: {resp.text}")
    
    device_data = resp.json()
    
    user_code = device_data["user_code"]              # 如：SPHDU6S5
    device_code = device_data["device_code"]          # 长字符串，用于轮询
    verification_uri = device_data["verification_uri"] # https://microsoft.com/link
    expires_in = device_data.get("expires_in", 900)   # 有效期（秒）
    interval = device_data.get("interval", 5)         # 轮询间隔（秒）
    
    # 步骤2：复制到剪贴板并打开浏览器（PCL2 做法）
    print(f"\n[2/5] 你的验证码: {user_code}")
    
    # 尝试复制到剪贴板
    try:
        import pyperclip
        pyperclip.copy(user_code)
        print("✓ 已自动复制到剪贴板")
    except ImportError:
        print("（未安装 pyperclip，请手动复制）")
        print(f"请手动复制: {user_code}")
    except Exception as e:
        print(f"（复制失败: {e}，请手动复制）")
    
    # 打开浏览器
    print(f"\n正在打开浏览器: {verification_uri}")
    print("请在打开的网页中粘贴验证码并完成登录...")
    webbrowser.open(verification_uri)
    
    # 步骤3：轮询获取 Token
    print(f"\n[3/5] 等待用户登录...")
    token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    token_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": CLIENT_ID,
        "device_code": device_code
    }
    
    start_time = time.time()
    while time.time() - start_time < expires_in:
        time.sleep(interval)
        
        token_resp = requests.post(token_url, data=token_data)
        token_json = token_resp.json()
        
        # 检查是否成功
        if "access_token" in token_json:
            print("✓ 登录成功！")
            return token_json["access_token"], token_json.get("refresh_token")
        
        # 处理错误
        error = token_json.get("error")
        if error == "authorization_pending":
            # 用户还没完成，继续等待
            print("等待用户完成登录...")
            continue
        elif error == "authorization_declined":
            raise Exception("用户拒绝了授权")
        elif error == "expired_token":
            raise Exception("设备代码已过期，请重试")
        elif error == "bad_verification_code":
            raise Exception("设备代码无效")
        else:
            # 其他错误
            if error:
                raise Exception(f"登录错误: {error} - {token_json.get('error_description', '')}")
    
    raise Exception("登录超时（15分钟），请重试")

# ========== Xbox/Minecraft 流程（保持不变）==========
def get_xbox_token(ms_token):
    url = "https://user.auth.xboxlive.com/user/authenticate"
    payload = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={ms_token}"
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT"
    }
    
    resp = requests.post(url, json=payload, headers={"x-xbl-contract-version": "1"})
    if resp.status_code != 200:
        raise Exception(f"XBL失败: {resp.text}")
    
    data = resp.json()
    return data["Token"], data["DisplayClaims"]["xui"][0]["uhs"]

def get_xsts(xbl_token):
    url = "https://xsts.auth.xboxlive.com/xsts/authorize"
    payload = {
        "Properties": {
            "SandboxId": "RETAIL",
            "UserTokens": [xbl_token]
        },
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT"
    }
    
    resp = requests.post(url, json=payload, headers={"x-xbl-contract-version": "1"})
    if resp.status_code != 200:
        error = resp.json()
        if error.get("XErr") == "2148916238":
            raise Exception("该账户未购买Minecraft或未创建Xbox档案")
        raise Exception(f"XSTS失败: {error}")
    
    data = resp.json()
    return data["Token"], data["DisplayClaims"]["xui"][0]["uhs"]

def get_minecraft_token(xsts_token, uhs):
    url = "https://api.minecraftservices.com/authentication/login_with_xbox"
    payload = {"identityToken": f"XBL3.0 x={uhs};{xsts_token}"}
    
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        raise Exception(f"Minecraft Token失败: {resp.text}")
    
    return resp.json()["access_token"]

# ========== 主程序 ==========
def main():
    print("=" * 60)
    print("Minecraft Microsoft Login - Device Code 模式")
    print("=" * 60)
    
    try:
        # 步骤1-3：Device Code 获取微软 Token
        ms_token, refresh = device_code_login()
        print("[4/5] 微软 Token 获取成功")
        
        # Xbox 流程
        xbl_token, uhs = get_xbox_token(ms_token)
        print("      Xbox Live Token 获取成功")
        
        xsts_token, _ = get_xsts(xbl_token)
        print("      XSTS Token 获取成功")
        
        # Minecraft Token
        mc_token = get_minecraft_token(xsts_token, uhs)
        print(f"[5/5] Minecraft Token 获取成功!")
        print(f"\n{'='*60}")
        print(f"Token: {mc_token}")
        print(f"{'='*60}")
        
        # 保存
        with open("minecraft_token.json", "w") as f:
            json.dump({
                "access_token": mc_token,
                "refresh_token": refresh,
                "timestamp": time.time()
            }, f, indent=2)
        
        print(f"\n已保存到 minecraft_token.json")
        
    except Exception as e:
        print(f"\n[致命错误] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()