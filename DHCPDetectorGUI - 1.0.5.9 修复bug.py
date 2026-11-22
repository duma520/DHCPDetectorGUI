import sys
import os
import json
import threading
import time
import socket
import subprocess
import re
from datetime import datetime
from collections import OrderedDict

# 添加这行代码来抑制 PyQt5 的弃用警告
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

class InterfaceScanner(QThread):
    """网络接口扫描线程"""
    interface_signal = pyqtSignal(list)
    progress_signal = pyqtSignal(int, str)
    
    def __init__(self):
        super().__init__()
        self.interfaces = []
        
    def get_all_interfaces(self):
        """获取所有网络接口"""
        interfaces = []
        
        try:
            # 方法1: 使用netifaces（如果可用）
            import netifaces
            all_ifaces = netifaces.interfaces()
            for iface in all_ifaces:
                # 修改：只排除明确的回环接口，不过滤其他接口
                if iface == 'lo' or iface.startswith('lo:'):
                    continue
                    
                try:
                    # 获取接口详细信息
                    addrs = netifaces.ifaddresses(iface)
                    
                    # 获取MAC地址
                    mac = ""
                    if netifaces.AF_LINK in addrs:
                        mac = addrs[netifaces.AF_LINK][0]['addr']
                    
                    # 获取IPv4地址
                    ip = "无IP"
                    if netifaces.AF_INET in addrs:
                        ip = addrs[netifaces.AF_INET][0]['addr']
                    
                    # 获取接口状态
                    status = self.get_interface_status(iface)
                
                    # 获取友好的接口名称
                    friendly_name = self.get_friendly_interface_name(iface)
                    
                    # 修改：在描述中显示原始接口名称
                    description = self.get_interface_description(iface)
                    if description:
                        description += f" | 原始接口: {iface}"
                    else:
                        description = f"原始接口: {iface}"
                    
                    interfaces.append({
                        'name': friendly_name,  # 使用友好名称
                        'original_name': iface,  # 保留原始名称
                        'mac': mac,
                        'ip': ip,
                        'status': status,
                        'description': description  # 修改：包含原始接口名称
                    })
                except Exception as e:
                    print(f"处理接口 {iface} 时出错: {e}")
                    friendly_name = self.get_friendly_interface_name(iface)
                    interfaces.append({
                        'name': friendly_name,
                        'original_name': iface,
                        'mac': '未知',
                        'ip': '未知',
                        'status': '未知',
                        'description': f'原始接口: {iface} | 错误: {str(e)}'  # 修改
                    })
            return interfaces
                    
        except ImportError:
            # 方法2: 使用系统命令（备用方法）
            return self.get_interfaces_system()


    
    def get_interface_status(self, interface):
        """获取接口状态"""
        try:
            # Linux系统
            if sys.platform.startswith('linux'):
                with open(f'/sys/class/net/{interface}/operstate', 'r') as f:
                    status = f.read().strip()
                    return '活动' if status == 'up' else '断开'
            
            # Windows系统
            elif sys.platform == 'win32':
                # 添加 startupinfo 来隐藏窗口
                startupinfo = None
                if sys.platform == 'win32':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    
                result = subprocess.run(
                    ['netsh', 'interface', 'show', 'interface', interface],
                    capture_output=True, text=True,
                    startupinfo=startupinfo
                )
                if '已连接' in result.stdout:
                    return '活动'
                elif '已断开连接' in result.stdout:
                    return '断开'
            

            
        except:
            pass
        
        return '未知'
    
    def get_interface_description(self, interface):
        """获取接口描述"""
        try:
            if sys.platform.startswith('linux'):
                # 尝试读取接口描述文件
                desc_file = f'/sys/class/net/{interface}/device/device'
                if os.path.exists(desc_file):
                    with open(desc_file, 'r') as f:
                        device_id = f.read().strip()
                        return f"设备ID: {device_id}"
                
                # 尝试从udev获取
                result = subprocess.run(
                    ['udevadm', 'info', '-q', 'property', '-p', f'/sys/class/net/{interface}'],
                    capture_output=True, text=True
                )
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'ID_NET_DRIVER=' in line:
                        driver = line.split('=')[1]
                        return f"驱动: {driver}"
        
        except:
            pass
        
        return ""
    
    def get_interfaces_system(self):
        """使用系统命令获取接口"""
        interfaces = []
        
        try:
            if sys.platform.startswith('linux'):
                # Linux: 使用ip命令
                result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
                lines = result.stdout.split('\n')
                
                current_iface = None
                for line in lines:
                    # 修改：改进接口行匹配，支持更多格式
                    if_match = re.search(r'^\d+:\s+([\w@.:-]+):', line)
                    if if_match:
                        current_iface = if_match.group(1)
                        # 修改：不过滤接口，只排除明确的回环接口
                        if current_iface != 'lo' and not current_iface.startswith('lo:'):
                            interfaces.append({
                                'name': current_iface,
                                'original_name': current_iface,
                                'mac': '',
                                'ip': '',
                                'status': '活动' if 'state UP' in line else '断开',
                                'description': ''
                            })
                    
                    # MAC地址行
                    elif current_iface and 'link/ether' in line:
                        mac_match = re.search(r'link/ether\s+([0-9a-f:]+)', line, re.IGNORECASE)
                        if mac_match and interfaces:
                            for iface in interfaces:
                                if iface['name'] == current_iface:
                                    iface['mac'] = mac_match.group(1)
                    
                    # IP地址行
                    elif current_iface and 'inet ' in line:
                        ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', line)
                        if ip_match and interfaces:
                            for iface in interfaces:
                                if iface['name'] == current_iface:
                                    iface['ip'] = ip_match.group(1)
            
            elif sys.platform == 'win32':
                # Windows: 使用 ipconfig
                startupinfo = None
                if sys.platform == 'win32':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                
                # 使用 gbk 编码处理中文
                result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True,
                                        startupinfo=startupinfo, encoding='gbk')
                lines = result.stdout.split('\n')
                
                current_adapter = None
                adapter_info = {}
                
                for i, line in enumerate(lines):
                    line = line.strip()
                    
                    # 修改：改进适配器名称匹配逻辑
                    # 匹配多种格式：适配器 xxx:、Ethernet adapter xxx:、Wireless LAN adapter xxx:
                    adapter_match = re.search(r'^(?:.*适配器\s+)?([^:]+):\s*$', line)
                    if adapter_match and ('适配器' in line or 'adapter' in line.lower()):
                        # 保存上一个适配器的信息
                        if current_adapter and adapter_info:
                            # 获取友好名称
                            friendly_name = self.get_friendly_interface_name(current_adapter)
                            if not friendly_name or friendly_name == current_adapter:
                                friendly_name = current_adapter
                            
                            # 修改：在描述中显示原始接口名称
                            description = adapter_info.get('description', friendly_name)
                            if description:
                                description += f" | 原始接口: {current_adapter}"
                            else:
                                description = f"原始接口: {current_adapter}"
                            
                            interfaces.append({
                                'name': friendly_name,
                                'original_name': current_adapter,
                                'mac': adapter_info.get('mac', ''),
                                'ip': adapter_info.get('ip', ''),
                                'status': '活动' if adapter_info.get('ip') else '断开',
                                'description': description  # 修改：包含原始接口名称
                            })
                        
                        # 提取适配器名称
                        adapter_name = adapter_match.group(1).strip()
                        
                        # 清理名称中的特殊字符
                        adapter_name = re.sub(r'[{}*]', '', adapter_name).strip()
                        
                        # 修改：不过滤接口，记录所有接口
                        if adapter_name:
                            current_adapter = adapter_name
                            adapter_info = {
                                'mac': '',
                                'ip': '',
                                'description': line.strip()
                            }
                        else:
                            current_adapter = None
                            adapter_info = {}
                    
                    # 物理地址
                    elif current_adapter and ('物理地址' in line or 'Physical Address' in line or 'MAC Address' in line):
                        # 查找物理地址
                        mac_match = re.search(r'([0-9A-F]{2}[:-]){5}([0-9A-F]{2})', line, re.IGNORECASE)
                        if mac_match:
                            adapter_info['mac'] = mac_match.group(0).replace('-', ':')
                    
                    # IPv4地址
                    elif current_adapter and ('IPv4 地址' in line or 'IPv4 Address' in line or 'IP Address' in line):
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if ip_match:
                            adapter_info['ip'] = ip_match.group(1)
                    
                    # 描述信息
                    elif current_adapter and ('描述' in line or 'Description' in line):
                        if ':' in line:
                            desc = line.split(':', 1)[1].strip()
                            if desc:
                                adapter_info['description'] = desc
                    
                    # 修改：添加对媒体状态的支持
                    elif current_adapter and ('媒体状态' in line or 'Media State' in line):
                        if '断开' in line or 'disconnected' in line.lower():
                            adapter_info['status'] = '断开'
                        elif '已连接' in line or 'connected' in line.lower():
                            adapter_info['status'] = '活动'
                
                # 添加最后一个适配器
                if current_adapter and adapter_info:
                    # 获取友好名称
                    friendly_name = self.get_friendly_interface_name(current_adapter)
                    if not friendly_name or friendly_name == current_adapter:
                        friendly_name = current_adapter
                    
                    # 修改：在描述中显示原始接口名称
                    description = adapter_info.get('description', friendly_name)
                    if description:
                        description += f" | 原始接口: {current_adapter}"
                    else:
                        description = f"原始接口: {current_adapter}"
                    
                    interfaces.append({
                        'name': friendly_name,
                        'original_name': current_adapter,
                        'mac': adapter_info.get('mac', ''),
                        'ip': adapter_info.get('ip', ''),
                        'status': adapter_info.get('status', '活动' if adapter_info.get('ip') else '断开'),
                        'description': description  # 修改：包含原始接口名称
                    })

            

        
        except Exception as e:
            print(f"获取接口时出错: {e}")
            # 修改：添加调试信息
            import traceback
            traceback.print_exc()
        
        return interfaces


    
    def run(self):
        """运行接口扫描"""
        try:
            self.progress_signal.emit(0, "正在扫描网络接口...")
            
            # 获取所有接口
            self.progress_signal.emit(30, "获取接口列表...")
            interfaces = self.get_all_interfaces()
            
            # 修改：添加调试输出
            print(f"扫描到 {len(interfaces)} 个接口:")
            for iface in interfaces:
                print(f"  - {iface['name']} (原始: {iface.get('original_name', 'N/A')})")
            
            # 处理接口信息
            self.progress_signal.emit(70, "处理接口信息...")
            
            # 去重并排序
            unique_interfaces = []
            seen = set()
            for iface in interfaces:
                if iface['name'] not in seen:
                    seen.add(iface['name'])
                    unique_interfaces.append(iface)
            
            # 按接口类型排序（有线优先）
            sorted_interfaces = sorted(unique_interfaces, 
                                    key=lambda x: (1 if x['name'].startswith(('eth', 'en', 'em', 'Ethernet')) else 
                                                2 if x['name'].startswith(('wlan', 'wl', 'wlp', 'Wi-Fi', 'Wireless')) else 
                                                3 if 'loopback' in x['description'].lower() else 4))
            
            self.progress_signal.emit(100, "扫描完成")
            self.interface_signal.emit(sorted_interfaces)
            
        except Exception as e:
            print(f"接口扫描失败: {e}")
            import traceback
            traceback.print_exc()
            self.interface_signal.emit([])


    def get_friendly_interface_name(self, interface):
        """获取友好的接口名称"""
        try:
            # 检查是否是 GUID 格式的接口名称
            guid_pattern = r'\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}'
            if re.match(guid_pattern, interface, re.IGNORECASE):
                # 这是 GUID 格式的接口，需要获取友好名称
                if sys.platform == 'win32':
                    return self.get_windows_friendly_name_for_guid(interface)
            
            if sys.platform == 'win32':
                # Windows: 尝试获取更友好的名称
                startupinfo = None
                if sys.platform == 'win32':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                
                # 使用 netsh 获取更详细的接口信息
                result = subprocess.run(
                    ['netsh', 'interface', 'show', 'interface'],
                    capture_output=True, text=True,
                    startupinfo=startupinfo, encoding='gbk'
                )
                
                lines = result.stdout.split('\n')
                for line in lines:
                    # 修改：改进匹配逻辑
                    if interface in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            # 提取接口名称
                            name = ' '.join(parts[3:])
                            name = re.sub(r'[{}*]', '', name).strip()
                            if name:
                                return name
                
                # 修改：如果netsh失败，尝试使用wmic
                try:
                    result = subprocess.run(
                        ['wmic', 'nic', 'get', 'NetConnectionID,Name'],
                        capture_output=True, text=True,
                        startupinfo=startupinfo, encoding='gbk'
                    )
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if interface in line:
                            parts = line.split()
                            if len(parts) >= 2:
                                return parts[-1]
                except:
                    pass
                
            elif sys.platform.startswith('linux'):
                # Linux: 尝试获取接口描述
                try:
                    # 尝试读取接口别名
                    alias_file = f'/sys/class/net/{interface}/ifalias'
                    if os.path.exists(alias_file):
                        with open(alias_file, 'r') as f:
                            alias = f.read().strip()
                            if alias:
                                return f"{interface} ({alias})"
                    
                    # 尝试读取设备信息
                    device_file = f'/sys/class/net/{interface}/device/device'
                    if os.path.exists(device_file):
                        with open(device_file, 'r') as f:
                            device_id = f.read().strip()
                            return f"{interface} (设备: {device_id})"
                except:
                    pass
            
        except Exception as e:
            print(f"获取友好接口名称失败: {e}")
        
        return interface

    def get_windows_friendly_name_for_guid(self, guid_interface):
        """获取Windows GUID接口的友好名称"""
        try:
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            # 方法1: 使用powershell获取网络适配器信息
            ps_command = f"""
            Get-NetAdapter | Where-Object {{ $_.InterfaceDescription -like '*{guid_interface}*' }} | 
            Select-Object Name, InterfaceDescription, InterfaceAlias | Format-List
            """
            
            result = subprocess.run(
                ['powershell', '-Command', ps_command],
                capture_output=True, text=True,
                startupinfo=startupinfo, encoding='gbk'
            )
            
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Name' in line and ':' in line:
                    name = line.split(':', 1)[1].strip()
                    if name and name != guid_interface:
                        return name
            
            # 方法2: 使用reg查询注册表
            try:
                reg_path = f"HKLM\\SYSTEM\\CurrentControlSet\\Control\\Network\\{{4D36E972-E325-11CE-BFC1-08002BE10318}}\\{guid_interface}\\Connection"
                result = subprocess.run(
                    ['reg', 'query', reg_path, '/v', 'Name'],
                    capture_output=True, text=True,
                    startupinfo=startupinfo, encoding='gbk'
                )
                
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'REG_SZ' in line:
                        name = line.split('REG_SZ')[1].strip()
                        if name:
                            return name
            except:
                pass
            
        except Exception as e:
            print(f"获取Windows GUID接口友好名称失败: {e}")
        
        # 如果无法获取友好名称，返回一个默认的友好名称
        return f"网络适配器 ({guid_interface})"


    def get_interfaces_fallback(self):
        """备用方法获取接口（使用socket）"""
        interfaces = []
        
        try:
            # 使用socket获取所有接口
            import socket
            import fcntl
            import struct
            
            # 获取所有接口名称
            max_iface = 10  # 假设最多10个接口
            for i in range(max_iface):
                try:
                    # 尝试获取接口信息
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    ifname = f'eth{i}'.encode('utf-8')
                    
                    # 获取IP地址
                    ip = socket.inet_ntoa(fcntl.ioctl(
                        sock.fileno(),
                        0x8915,  # SIOCGIFADDR
                        struct.pack('256s', ifname[:15])
                    )[20:24])
                    
                    # 获取MAC地址
                    mac = fcntl.ioctl(
                        sock.fileno(),
                        0x8927,  # SIOCGIFHWADDR
                        struct.pack('256s', ifname[:15])
                    )[18:24]
                    mac = ':'.join(['%02x' % b for b in mac])
                    
                    interfaces.append({
                        'name': f'eth{i}',
                        'original_name': f'eth{i}',
                        'mac': mac,
                        'ip': ip,
                        'status': '活动',
                        'description': '通过socket获取'
                    })
                    
                    sock.close()
                except:
                    continue
        except:
            pass
        
        return interfaces



class DHCPDetector(QThread):
    """DHCP检测线程"""
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.is_running = True
        self.interface = ""
        self.timeout = 5
        self.retry_count = 3
        
    def set_parameters(self, interface, timeout=5, retry_count=3):
        """设置检测参数"""
        self.interface = interface
        self.timeout = timeout
        self.retry_count = retry_count
    
    def get_local_ip(self):
        """获取本地IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "未知"
    
    def get_mac_address(self, interface):
        """获取MAC地址"""
        try:
            import netifaces
            mac = netifaces.ifaddresses(interface)[netifaces.AF_LINK][0]['addr']
            return mac
        except:
            try:
                # 备用方法
                import uuid
                mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                              for elements in range(0,8*6,8)][::-1])
                return mac
            except:
                return "未知"
    
    def check_dhcp_service(self):
        """检查DHCP服务状态"""
        try:
            # 尝试多种方法检测DHCP服务
            methods = [
                self._check_dhcp_via_nmap,
                self._check_dhcp_via_dhcpdump,
                self._check_dhcp_via_tcpdump
            ]
            
            for method in methods:
                result = method()
                if result["status"] != "未知":
                    return result
            
            return {"status": "未知", "message": "无法检测DHCP服务状态"}
        except Exception as e:
            return {"status": "错误", "message": str(e)}
    
    def _check_dhcp_via_nmap(self):
        """通过nmap检测DHCP"""
        try:
            cmd = ["nmap", "--script", "broadcast-dhcp-discover"]
        
            # 隐藏控制台窗口
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                    timeout=self.timeout, startupinfo=startupinfo)
                
            if "DHCPACK" in result.stdout:
                return {"status": "运行中", "message": "发现DHCP服务响应"}
            elif "DHCPOFFER" in result.stdout:
                return {"status": "运行中", "message": "收到DHCP提供"}
            else:
                return {"status": "未响应", "message": "未收到DHCP响应"}
        except:
            return {"status": "未知", "message": "nmap检测失败"}
    
    def _check_dhcp_via_dhcpdump(self):
        """通过dhcpdump检测DHCP"""
        try:
            cmd = ["timeout", str(self.timeout), "dhcpdump", "-i", self.interface]
        
            # 隐藏控制台窗口
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                    startupinfo=startupinfo)

            if "DHCP" in result.stdout:
                return {"status": "运行中", "message": "检测到DHCP流量"}
            else:
                return {"status": "未响应", "message": "未检测到DHCP流量"}
        except:
            return {"status": "未知", "message": "dhcpdump不可用"}
    
    def _check_dhcp_via_tcpdump(self):
        """通过tcpdump检测DHCP"""
        try:
            cmd = ["timeout", str(self.timeout), "tcpdump", "-i", self.interface, 
                   "port", "67", "or", "port", "68", "-c", "5"]
        
            # 隐藏控制台窗口
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                    startupinfo=startupinfo)
            
            if "BOOTP/DHCP" in result.stdout:
                return {"status": "运行中", "message": "检测到DHCP数据包"}
            else:
                return {"status": "未响应", "message": "未检测到DHCP数据包"}
        except:
            return {"status": "未知", "message": "tcpdump检测失败"}
    
    def get_dhcp_info(self):
        """获取DHCP信息"""
        try:
            # 获取当前IP配置
            local_ip = self.get_local_ip()
            mac = self.get_mac_address(self.interface)
            
            # 获取网关
            gateway = "未知"
            try:
                import netifaces
                gws = netifaces.gateways()
                gateway = gws['default'][netifaces.AF_INET][0]
            except:
                pass
            
            # 获取DNS服务器
            dns_servers = []
            try:
                with open('/etc/resolv.conf', 'r') as f:
                    for line in f:
                        if line.startswith('nameserver'):
                            dns_servers.append(line.split()[1])
            except:
                dns_servers = ["未知"]
            
            return {
                "local_ip": local_ip,
                "mac_address": mac,
                "gateway": gateway,
                "dns_servers": dns_servers,
                "interface": self.interface
            }
        except Exception as e:
            return {
                "local_ip": "未知",
                "mac_address": "未知",
                "gateway": "未知",
                "dns_servers": ["未知"],
                "interface": self.interface,
                "error": str(e)
            }
    
    def run(self):
        """运行检测"""
        try:
            if not self.interface:
                self.error_signal.emit("请选择网络接口")
                return
            
            total_steps = 4
            current_step = 0
            
            # 步骤1: 检查网络接口
            self.progress_signal.emit(25, "正在检查网络接口...")
            current_step += 1
            time.sleep(0.5)
            
            # 步骤2: 获取网络信息
            self.progress_signal.emit(50, "正在获取网络信息...")
            current_step += 1
            dhcp_info = self.get_dhcp_info()
            time.sleep(0.5)
            
            # 步骤3: 检查DHCP服务
            self.progress_signal.emit(75, "正在检测DHCP服务...")
            current_step += 1
            dhcp_status = self.check_dhcp_service()
            time.sleep(0.5)
            
            # 步骤4: 汇总结果
            self.progress_signal.emit(100, "正在生成报告...")
            
            # 合并结果
            result = {
                **dhcp_info,
                "dhcp_status": dhcp_status["status"],
                "dhcp_message": dhcp_status["message"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "interface": self.interface
            }
            
            self.result_signal.emit(result)
            
        except Exception as e:
            self.error_signal.emit(f"检测过程中发生错误: {str(e)}")

class InterfaceScannerWidget(QWidget):
    """网络接口扫描器部件"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 顶部按钮
        top_layout = QHBoxLayout()
        
        self.scan_button = QPushButton("扫描所有接口")
        self.scan_button.setIcon(QApplication.style().standardIcon(QStyle.SP_BrowserReload))
        self.scan_button.clicked.connect(self.start_scanning)
        
        self.refresh_button = QPushButton("刷新选中接口")
        self.refresh_button.setEnabled(False)
        
        top_layout.addWidget(self.scan_button)
        top_layout.addWidget(self.refresh_button)
        top_layout.addStretch()
        
        # 接口表格
        self.interface_table = QTableWidget()
        self.interface_table.setColumnCount(6)
        self.interface_table.setHorizontalHeaderLabels(["选择", "接口名称", "IP地址", "MAC地址", "状态", "描述"])
        self.interface_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.interface_table.setSelectionMode(QTableWidget.SingleSelection)
        self.interface_table.verticalHeader().setVisible(False)
        self.interface_table.setAlternatingRowColors(True)
        
        # 设置列宽
        header = self.interface_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        
        # 进度条
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.scan_status = QLabel()
        
        layout.addLayout(top_layout)
        layout.addWidget(self.interface_table)
        layout.addWidget(self.scan_progress)
        layout.addWidget(self.scan_status)
        
    def start_scanning(self):
        """开始扫描所有接口"""
        self.scanner = InterfaceScanner()
        self.scanner.interface_signal.connect(self.update_interface_table)
        self.scanner.progress_signal.connect(self.update_scan_progress)
        self.scanner.start()
        
        # 更新UI状态
        self.scan_button.setEnabled(False)
        self.scan_progress.setVisible(True)
        self.scan_status.setText("正在扫描网络接口...")
        
    def update_scan_progress(self, value, message):
        """更新扫描进度"""
        self.scan_progress.setValue(value)
        self.scan_status.setText(message)
        
        if value == 100:
            self.scan_button.setEnabled(True)
            self.scan_progress.setVisible(False)
    
    def update_interface_table(self, interfaces):
        """更新接口表格"""
        self.interface_table.setRowCount(len(interfaces))
        
        for i, iface in enumerate(interfaces):
            # 选择复选框
            checkbox = QCheckBox()
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.interface_table.setCellWidget(i, 0, checkbox_widget)
            
            # 接口名称（显示友好名称）
            name_item = QTableWidgetItem(iface['name'])
            # 存储原始名称到 UserRole
            name_item.setData(Qt.UserRole, iface.get('original_name', iface['name']))
            
            # 如果原始名称是GUID格式，在名称后面添加提示
            guid_pattern = r'\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}'
            original_name = iface.get('original_name', iface['name'])
            if re.match(guid_pattern, original_name, re.IGNORECASE):
                name_item.setText(f"{iface['name']} (GUID)")
                name_item.setToolTip(f"原始接口名称: {original_name}")
            
            self.interface_table.setItem(i, 1, name_item)
            
            # IP地址
            ip_item = QTableWidgetItem(iface['ip'])
            self.interface_table.setItem(i, 2, ip_item)
            
            # MAC地址
            mac_item = QTableWidgetItem(iface['mac'])
            self.interface_table.setItem(i, 3, mac_item)
            
            # 状态
            status_item = QTableWidgetItem(iface['status'])
            if iface['status'] == '活动':
                status_item.setForeground(QColor('green'))
                status_item.setFont(QFont('', weight=QFont.Bold))
            elif iface['status'] == '断开':
                status_item.setForeground(QColor('red'))
            else:
                status_item.setForeground(QColor('gray'))
            self.interface_table.setItem(i, 4, status_item)
            
            # 描述 - 确保包含原始接口名称
            description = iface.get('description', '')
            
            # 如果描述中还没有包含原始接口名称，则添加
            original_name = iface.get('original_name', iface['name'])
            if f"原始接口: {original_name}" not in description:
                if description:
                    description += f" | 原始接口: {original_name}"
                else:
                    description = f"原始接口: {original_name}"
            
            # 如果是GUID格式，添加特殊标记
            guid_pattern = r'\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}'
            if re.match(guid_pattern, original_name, re.IGNORECASE):
                description += " [GUID格式]"
            
            desc_item = QTableWidgetItem(description)
            desc_item.setToolTip(f"完整描述: {description}")
            self.interface_table.setItem(i, 5, desc_item)
        
        # 更新状态标签
        guid_count = 0
        for iface in interfaces:
            original_name = iface.get('original_name', iface['name'])
            guid_pattern = r'\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}'
            if re.match(guid_pattern, original_name, re.IGNORECASE):
                guid_count += 1
        
        status_text = f"扫描完成，共发现 {len(interfaces)} 个网络接口"
        if guid_count > 0:
            status_text += f"（其中 {guid_count} 个为GUID格式接口）"
        
        self.scan_status.setText(status_text)
        
        # 自动选择第一个活动接口
        for row in range(self.interface_table.rowCount()):
            status_item = self.interface_table.item(row, 4)
            if status_item and status_item.text() == '活动':
                widget = self.interface_table.cellWidget(row, 0)
                if widget:
                    widget.layout().itemAt(0).widget().setChecked(True)
                break

    
    def get_selected_interface(self):
        """获取选中的接口"""
        for row in range(self.interface_table.rowCount()):
            widget = self.interface_table.cellWidget(row, 0)
            if widget and widget.layout().itemAt(0).widget().isChecked():
                # 获取原始接口名称
                item = self.interface_table.item(row, 1)
                if item:
                    # 这里需要存储原始名称，可以在 item 的 data 中存储
                    original_name = item.data(Qt.UserRole)
                    return original_name if original_name else item.text()
        return None

    
    def select_interface(self, interface_name):
        """选择指定接口"""
        for row in range(self.interface_table.rowCount()):
            item = self.interface_table.item(row, 1)
            if item and item.text() == interface_name:
                widget = self.interface_table.cellWidget(row, 0)
                if widget:
                    widget.layout().itemAt(0).widget().setChecked(True)
                break

class DHCPDetectionTool(QMainWindow):
    """DHCP检测工具主窗口"""
    
    def __init__(self):
        super().__init__()
        self.settings_file = "dhcp_detector_settings.json"
        self.detector = None
        self.init_ui()
        self.load_settings()
        self.setup_icon()
        
    def setup_icon(self):
        """设置窗口图标"""
        if os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("DHCP检测工具")
        self.setGeometry(100, 100, 1000, 800)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # 创建选项卡
        self.tab_widget = QTabWidget()
        
        # 选项卡1: 接口扫描
        self.interface_scanner_widget = InterfaceScannerWidget()
        self.tab_widget.addTab(self.interface_scanner_widget, "网络接口扫描")
        
        # 选项卡2: DHCP检测
        self.dhcp_detection_widget = self.create_dhcp_detection_widget()
        self.tab_widget.addTab(self.dhcp_detection_widget, "DHCP检测")
        
        main_layout.addWidget(self.tab_widget)
        
        # 设置样式
        self.set_style()
        
        # 连接信号
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
    
    def create_dhcp_detection_widget(self):
        """创建DHCP检测部件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 控制面板
        control_group = QGroupBox("检测设置")
        control_layout = QGridLayout()
        
        # 网络接口选择（简化版，实际从扫描器获取）
        interface_label = QLabel("网络接口:")
        self.interface_combo = QComboBox()
        self.interface_combo.setEditable(True)
        
        # 从扫描器选择按钮
        select_from_scanner_btn = QPushButton("从扫描器选择")
        select_from_scanner_btn.clicked.connect(self.select_from_scanner)
        
        # 超时设置
        timeout_label = QLabel("超时时间(秒):")
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setValue(5)
        
        # 重试次数
        retry_label = QLabel("重试次数:")
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(1, 10)
        self.retry_spin.setValue(3)
        
        control_layout.addWidget(interface_label, 0, 0)
        control_layout.addWidget(self.interface_combo, 0, 1)
        control_layout.addWidget(select_from_scanner_btn, 0, 2)
        control_layout.addWidget(timeout_label, 1, 0)
        control_layout.addWidget(self.timeout_spin, 1, 1)
        control_layout.addWidget(retry_label, 2, 0)
        control_layout.addWidget(self.retry_spin, 2, 1)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # 进度条区域
        progress_group = QGroupBox("检测进度")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # 结果展示区域
        result_group = QGroupBox("检测结果")
        result_layout = QVBoxLayout()
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(300)
        
        result_layout.addWidget(self.result_text)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("开始检测")
        self.start_button.clicked.connect(self.start_detection)
        self.start_button.setMinimumHeight(40)
        
        self.stop_button = QPushButton("停止检测")
        self.stop_button.clicked.connect(self.stop_detection)
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumHeight(40)
        
        self.save_button = QPushButton("保存结果")
        self.save_button.clicked.connect(self.save_results)
        self.save_button.setMinimumHeight(40)
        
        self.clear_button = QPushButton("清除结果")
        self.clear_button.clicked.connect(self.clear_results)
        self.clear_button.setMinimumHeight(40)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.clear_button)
        layout.addLayout(button_layout)
        
        return widget
    
    def select_from_scanner(self):
        """从扫描器选择接口"""
        selected = self.interface_scanner_widget.get_selected_interface()
        if selected:
            # 切换到DHCP检测选项卡
            self.tab_widget.setCurrentIndex(1)
            
            # 更新接口选择框
            index = self.interface_combo.findText(selected)
            if index >= 0:
                self.interface_combo.setCurrentIndex(index)
            else:
                self.interface_combo.setCurrentText(selected)
        else:
            QMessageBox.warning(self, "警告", "请在网络接口扫描页面选择一个接口")
            self.tab_widget.setCurrentIndex(0)
    
    def on_tab_changed(self, index):
        """选项卡切换事件"""
        if index == 0:  # 切换到接口扫描选项卡
            # 自动开始扫描
            self.interface_scanner_widget.start_scanning()
    
    def set_style(self):
        """设置界面样式"""
        style = """
        QMainWindow {
            background-color: #f5f5f5;
        }
        QTabWidget::pane {
            border: 1px solid #cccccc;
            background-color: white;
        }
        QTabBar::tab {
            background-color: #e0e0e0;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected {
            background-color: white;
            font-weight: bold;
        }
        QTabBar::tab:hover {
            background-color: #d0d0d0;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #cccccc;
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QPushButton {
            background-color: #2196F3;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #1976D2;
        }
        QPushButton:disabled {
            background-color: #cccccc;
        }
        QPushButton#stop_button {
            background-color: #f44336;
        }
        QPushButton#stop_button:hover {
            background-color: #da190b;
        }
        QProgressBar {
            border: 1px solid #cccccc;
            border-radius: 3px;
            text-align: center;
            height: 20px;
        }
        QProgressBar::chunk {
            background-color: #4CAF50;
            border-radius: 3px;
        }
        QTextEdit {
            border: 1px solid #cccccc;
            border-radius: 3px;
            padding: 5px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 11px;
        }
        QLabel {
            padding: 2px;
        }
        QTableWidget {
            border: 1px solid #cccccc;
            border-radius: 3px;
            alternate-background-color: #f9f9f9;
        }
        QTableWidget::item {
            padding: 4px;
        }
        QHeaderView::section {
            background-color: #e0e0e0;
            padding: 4px;
            border: 1px solid #cccccc;
            font-weight: bold;
        }
        """
        self.setStyleSheet(style)
    
    def start_detection(self):
        """开始检测"""
        if self.detector and self.detector.isRunning():
            return
        
        interface = self.interface_combo.currentText()
        if not interface:
            QMessageBox.warning(self, "警告", "请选择网络接口")
            return
        
        # 创建检测线程
        self.detector = DHCPDetector()
        self.detector.set_parameters(
            interface=interface,
            timeout=self.timeout_spin.value(),
            retry_count=self.retry_spin.value()
        )
        
        # 连接信号
        self.detector.progress_signal.connect(self.update_progress)
        self.detector.result_signal.connect(self.show_results)
        self.detector.error_signal.connect(self.show_error)
        self.detector.finished.connect(self.detection_finished)
        
        # 更新UI状态
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("正在检测...")
        self.progress_bar.setValue(0)
        
        # 开始检测
        self.detector.start()
        
        # 保存设置
        self.save_settings()
    
    def stop_detection(self):
        """停止检测"""
        if self.detector and self.detector.isRunning():
            self.detector.is_running = False
            self.detector.terminate()
            self.detector.wait()
            self.status_label.setText("已停止")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
    
    def update_progress(self, value, message):
        """更新进度"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
    
    def show_results(self, results):
        """显示检测结果"""
        output = f"""
{'='*70}
DHCP检测报告
检测时间: {results.get('timestamp', '未知')}
{'='*70}

网络接口信息:
  接口名称: {results.get('interface', '未知')}
  MAC地址: {results.get('mac_address', '未知')}
  本地IP: {results.get('local_ip', '未知')}
  网关: {results.get('gateway', '未知')}
  DNS服务器: {', '.join(results.get('dns_servers', ['未知']))}

DHCP服务状态:
  状态: {results.get('dhcp_status', '未知')}
  消息: {results.get('dhcp_message', '未知')}

{'='*70}
"""
        self.result_text.append(output)
        
        # 滚动到底部
        cursor = self.result_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.result_text.setTextCursor(cursor)
        
        # 根据状态设置颜色
        if results.get('dhcp_status') == '运行中':
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.status_label.setText("DHCP服务正常")
        elif results.get('dhcp_status') == '未响应':
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.status_label.setText("DHCP服务未响应")
        else:
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.status_label.setText("DHCP服务检测失败")
    
    def show_error(self, error_message):
        """显示错误信息"""
        QMessageBox.critical(self, "错误", error_message)
        self.status_label.setText("检测失败")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
    
    def detection_finished(self):
        """检测完成"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
    
    def save_results(self):
        """保存检测结果"""
        if not self.result_text.toPlainText().strip():
            QMessageBox.warning(self, "警告", "没有结果可保存")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存结果", "dhcp_detection_result.txt", "文本文件 (*.txt)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.result_text.toPlainText())
                QMessageBox.information(self, "成功", f"结果已保存到: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")
    
    def clear_results(self):
        """清除结果"""
        reply = QMessageBox.question(
            self, "确认", "确定要清除所有结果吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.result_text.clear()
            self.progress_bar.setValue(0)
            self.status_label.setText("就绪")
            self.status_label.setStyleSheet("")
    
    def save_settings(self):
        """保存设置到文件"""
        settings = {
            "interface": self.interface_combo.currentText(),
            "timeout": self.timeout_spin.value(),
            "retry_count": self.retry_spin.value(),
            "window_geometry": {
                "width": self.width(),
                "height": self.height()
            },
            "last_tab": self.tab_widget.currentIndex()
        }
        
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存设置失败: {e}")
    
    def load_settings(self):
        """从文件加载设置"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 恢复界面设置
                if "interface" in settings:
                    interface = settings["interface"]
                    index = self.interface_combo.findText(interface)
                    if index >= 0:
                        self.interface_combo.setCurrentIndex(index)
                    else:
                        self.interface_combo.addItem(interface)
                        self.interface_combo.setCurrentText(interface)
                
                self.timeout_spin.setValue(settings.get("timeout", 5))
                self.retry_spin.setValue(settings.get("retry_count", 3))
                
                # 恢复窗口大小
                geometry = settings.get("window_geometry", {})
                if geometry:
                    self.resize(geometry.get("width", 1000), geometry.get("height", 800))
                
                # 恢复选项卡
                last_tab = settings.get("last_tab", 0)
                self.tab_widget.setCurrentIndex(last_tab)
                    
            except Exception as e:
                print(f"加载设置失败: {e}")
        else:
            # 首次运行，自动扫描接口
            QTimer.singleShot(500, lambda: self.interface_scanner_widget.start_scanning())
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        self.save_settings()
        
        # 停止正在运行的检测
        if self.detector and self.detector.isRunning():
            self.detector.is_running = False
            self.detector.terminate()
            self.detector.wait()
        
        event.accept()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("DHCP检测工具")
    
    # 设置应用程序图标（如果存在）
    if os.path.exists("icon.ico"):
        app.setWindowIcon(QIcon("icon.ico"))
    
    # 创建并显示主窗口
    window = DHCPDetectionTool()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    # 检查依赖
    dependencies = ['PyQt5', 'netifaces']
    
    for dep in dependencies:
        try:
            if dep == 'PyQt5':
                import PyQt5
            elif dep == 'netifaces':
                import netifaces
        except ImportError:
            print(f"正在安装依赖库: {dep}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            except:
                print(f"安装{dep}失败，请手动安装: pip install {dep}")
                if dep == 'netifaces':
                    print("注意: netifaces库在某些系统上可能需要编译工具")
    
    main()