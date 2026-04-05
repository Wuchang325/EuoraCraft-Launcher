import sys
from pathlib import Path

# 先加路径再导入
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ECL.Game.MicrosoftAuth import MultiAccountMinecraftAuth


def log(msg: str) -> None:
    print(f"[Auth] {msg}")


def login_log(msg: str) -> None:
    print(f"[Login] {msg}")


def show_device_code(flow: dict) -> None:
    print("\n" + "=" * 50)
    print("请在浏览器中完成登录：")
    print(f"  访问：{flow['verification_uri']}")
    print(f"  输入代码：{flow['user_code']}")
    print("=" * 50 + "\n")


def ask_password() -> str:
    # 首次运行设置主密码
    while True:
        pwd = input("设置主密码（至少8位）：")
        if len(pwd) >= 8:
            confirm = input("确认密码：")
            if pwd == confirm:
                return pwd
            print("两次输入不一致")
        else:
            print("密码太短")


def main():
    # 微软应用 ID（测试用，生产环境建议换成自己的）
    client_id = "f1709935-df0b-400c-843a-530a77fb8d3c"
    
    auth = MultiAccountMinecraftAuth(client_id)
    
    # 设置回调
    auth.set_output_log(log)
    auth.set_output_login_log(login_log)
    auth.set_login_callback(show_device_code)
    auth.set_first_launch_callback(ask_password)
    
    # 初始化（首次会要求设置主密码）
    log("正在初始化...")
    if not auth.initialize():
        log("初始化失败")
        return
    
    log(f"当前密钥环后端: {auth.encryption.keyring_manager.backend_type}")
    
    # 添加账户（设备代码流登录）
    log("开始添加账户...")
    if auth.add_account():
        log("账户添加成功")
        
        # 获取启动令牌
        token = auth.get_current_account_token()
        if token:
            log(f"获取到 Minecraft 令牌：{token[:20]}...")
            
            # 获取档案
            profile = auth.get_current_account_profile()
            if profile:
                log(f"玩家：{profile['name']} (UUID: {profile['id']})")
    else:
        log("账户添加失败")


if __name__ == "__main__":
    main()