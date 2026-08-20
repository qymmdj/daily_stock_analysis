import sys
import os
import winreg
import subprocess
from typing import Optional, List, Dict
from datetime import datetime


def find_tdx_process() -> Optional[str]:
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq TdxW.exe', '/FO', 'LIST'],
            capture_output=True,
            text=True,
            encoding='gbk'
        )
        if 'TdxW.exe' in result.stdout:
            return 'TdxW.exe'
    except Exception:
        pass
    return None


def get_tdx_process_path() -> Optional[str]:
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='TdxW.exe'", 'get', 'ExecutablePath'],
            capture_output=True,
            text=True,
            encoding='gbk'
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 2 and lines[1].strip():
            return lines[1].strip()
    except Exception:
        pass
    return None


def get_tdx_install_path() -> Optional[str]:
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\通达信金融终端64"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
            return install_path
    except FileNotFoundError:
        return None


def check_tqcenter_exists(tdx_root: str) -> bool:
    tqcenter_path = os.path.join(tdx_root, 'PYPlugins', 'user', 'tqcenter.py')
    return os.path.exists(tqcenter_path)


def get_tdx_root() -> Optional[str]:
    known_paths = [
        r"C:\new_tdx64",
        r"C:\new_tdx",
        r"D:\new_tdx64",
        r"D:\new_tdx",
        r"E:\new_tdx64",
        r"E:\new_tdx",
        r"C:\tdxw",
        r"D:\tdxw",
    ]

    print(f"检查常见路径...")
    for path in known_paths:
        print(f"  检查: {path} -> {os.path.exists(path)}")
        if os.path.exists(path):
            pyplugins_path = os.path.join(path, 'PYPlugins')
            user_path = os.path.join(path, 'PYPlugins', 'user')
            tqcenter_path = os.path.join(path, 'PYPlugins', 'user', 'tqcenter.py')
            print(f"    PYPlugins存在: {os.path.exists(pyplugins_path)}")
            print(f"    user存在: {os.path.exists(user_path)}")
            print(f"    tqcenter.py存在: {os.path.exists(tqcenter_path)}")
        if check_tqcenter_exists(path):
            print(f"找到通达信安装目录: {path}")
            return path

    tdx_root = get_tdx_install_path()
    if tdx_root and check_tqcenter_exists(tdx_root):
        print(f"从注册表获取通达信安装目录: {tdx_root}")
        return tdx_root

    tdx_process = find_tdx_process()
    if tdx_process:
        process_path = get_tdx_process_path()
        if process_path:
            exe_dir = os.path.dirname(process_path)
            if check_tqcenter_exists(exe_dir):
                print(f"通过进程路径找到通达信安装目录: {exe_dir}")
                return exe_dir

    print("错误: 找不到tqcenter.py文件，请确认通达信客户端已正确安装")
    return None


def initialize_tq() -> Optional[object]:
    tdx_root = get_tdx_root()
    if not tdx_root:
        return None

    tqcenter_path = os.path.join(tdx_root, 'PYPlugins', 'user')
    if tqcenter_path not in sys.path:
        sys.path.insert(0, tqcenter_path)

    try:
        from tqcenter import tq
        tq.initialize(__file__)
        print("TQ初始化成功")
        return tq
    except Exception as e:
        print(f"TQ初始化失败: {e}")
        return None


def get_realtime_kline(
    tq,
    stock_codes: List[str],
    period: str = '1d',
    count: int = 100,
    dividend_type: str = 'front'
) -> Dict:
    try:
        data = tq.get_market_data(
            field_list=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Amount'],
            stock_list=stock_codes,
            period=period,
            count=count,
            dividend_type=dividend_type,
            fill_data=True
        )
        return data
    except Exception as e:
        print(f"获取K线数据失败: {e}")
        return {}


def print_kline_data(data: Dict, stock_code: str):
    import pandas as pd

    if not data or stock_code not in data.get('Close', pd.DataFrame()).columns:
        print(f"没有获取到 {stock_code} 的数据")
        return

    close_df = data['Close'][stock_code]
    open_df = data['Open'][stock_code]
    high_df = data['High'][stock_code]
    low_df = data['Low'][stock_code]
    volume_df = data['Volume'][stock_code]

    print(f"\n{'='*60}")
    print(f"股票: {stock_code}")
    print(f"{'='*60}")
    print(f"{'日期':<12} {'开盘':<10} {'收盘':<10} {'最高':<10} {'最低':<10} {'成交量':<15}")
    print(f"{'-'*60}")

    for i in range(len(close_df) - 1, -1, -1):
        date = close_df.index[i]
        close = close_df.iloc[i]
        open_price = open_df.iloc[i]
        high = high_df.iloc[i]
        low = low_df.iloc[i]
        volume = volume_df.iloc[i]

        print(f"{str(date):<12} {open_price:<10.2f} {close:<10.2f} {high:<10.2f} {low:<10.2f} {volume:<15.0f}")

        if len(close_df) - 1 - i >= 9:
            print("...")
            break


def main():
    print("通达信K线数据获取程序")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)

    tq = initialize_tq()
    if not tq:
        sys.exit(1)

    try:
        stock_codes = ['600519.SH', '000001.SZ', '688318.SH']

        print(f"\n获取股票K线数据: {stock_codes}")
        print(f"K线周期: 日线 (1d)")
        print(f"复权类型: 前复权")

        data = get_realtime_kline(tq, stock_codes, period='1d', count=10)

        if data:
            for code in stock_codes:
                print_kline_data(data, code)
        else:
            print("未能获取到任何数据")

    finally:
        tq.close()
        print("\n连接已关闭")


if __name__ == '__main__':
    main()