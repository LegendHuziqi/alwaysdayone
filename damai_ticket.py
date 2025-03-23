from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import os
import json
import ddddocr
from dotenv import load_dotenv
import logging
import random
from datetime import datetime

class DamaiTicket:
    def __init__(self):
        self.setup_logging()
        self.config = self.load_config()
        self.driver = None
        self.wait = None
        self.ocr = ddddocr.DdddOcr()
        self.max_retries = 3
        
    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('ticket.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def load_config(self):
        """加载配置文件"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.logger.info("配置文件加载成功")
                return config
        except FileNotFoundError:
            self.logger.warning("配置文件不存在，创建默认配置")
            default_config = {
                "url": "",  # 演出详情页链接
                "ticket_num": 1,  # 购票数量
                "real_name": [],  # 实名者列表
                "price_preference": [],  # 价格优先级，从高到低
                "session": {
                    "cookies": None
                },
                "refresh_interval": [0.5, 1],  # 刷新间隔范围（秒）
                "max_retries": 3  # 最大重试次数
            }
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            return default_config

    def init_driver(self):
        """初始化浏览器驱动"""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            })
            self.wait = WebDriverWait(self.driver, 10)
            self.logger.info("浏览器初始化成功")
        except Exception as e:
            self.logger.error(f"浏览器初始化失败: {str(e)}")
            raise
        
    def login(self):
        """登录大麦网"""
        self.logger.info("开始登录流程")
        self.driver.get("https://www.damai.cn")
        
        if self.config['session']['cookies']:
            try:
                for cookie in self.config['session']['cookies']:
                    self.driver.add_cookie(cookie)
                self.driver.refresh()
                self.logger.info("使用已保存的cookies登录成功")
            except Exception as e:
                self.logger.error(f"使用cookies登录失败: {str(e)}")
                self.manual_login()
        else:
            self.manual_login()

    def manual_login(self):
        """手动登录流程"""
        self.logger.info("请在30秒内完成手动登录")
        time.sleep(30)
        
        try:
            cookies = self.driver.get_cookies()
            self.config['session']['cookies'] = cookies
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            self.logger.info("登录cookies保存成功")
        except Exception as e:
            self.logger.error(f"保存cookies失败: {str(e)}")

    def refresh_page(self):
        """智能刷新页面"""
        interval = random.uniform(
            self.config.get('refresh_interval', [0.5, 1])[0],
            self.config.get('refresh_interval', [0.5, 1])[1]
        )
        time.sleep(interval)
        self.driver.refresh()
        self.logger.debug(f"页面刷新，间隔{interval:.2f}秒")

    def select_ticket(self):
        """选择门票"""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                self.driver.get(self.config['url'])
                time.sleep(1)

                # 等待价格列表加载
                price_list = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".select_right_list_item"))
                )
                
                # 根据价格优先级选择
                for prefer_price in self.config['price_preference']:
                    for price in price_list:
                        if str(prefer_price) in price.text and "缺货" not in price.text:
                            price.click()
                            self.logger.info(f"选择票价：{prefer_price}")
                            return True
                
                self.logger.warning("所选票价均无票")
                self.refresh_page()
                retry_count += 1
            except Exception as e:
                self.logger.error(f"选择门票失败: {str(e)}")
                retry_count += 1
                if retry_count < self.max_retries:
                    self.refresh_page()
                
        return False

    def select_buyer(self):
        """选择购票人"""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                # 等待实名者列表加载
                buyer_list = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".buyer-list-item"))
                )
                
                # 选择对应的实名者
                selected = False
                for buyer in buyer_list:
                    buyer_name = buyer.find_element(By.CSS_SELECTOR, ".buyer-name").text
                    if buyer_name in self.config['real_name']:
                        buyer.click()
                        selected = True
                        self.logger.info(f"选择购票人：{buyer_name}")
                
                if selected:
                    return True
                else:
                    self.logger.warning("未找到配置的实名购票人")
                    retry_count += 1
                    
            except Exception as e:
                self.logger.error(f"选择购票人失败: {str(e)}")
                retry_count += 1
                if retry_count < self.max_retries:
                    time.sleep(0.5)
                
        return False

    def submit_order(self):
        """提交订单"""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                # 同意协议
                agree_button = self.wait.until(
                    EC.element_to_be_clickable((By.CLASS_NAME, "service-checkbox"))
                )
                agree_button.click()
                
                # 提交订单
                submit_button = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".submit-button"))
                )
                submit_button.click()
                self.logger.info("订单提交成功")
                return True
            except Exception as e:
                self.logger.error(f"提交订单失败: {str(e)}")
                retry_count += 1
                if retry_count < self.max_retries:
                    time.sleep(0.5)
                
        return False

    def run(self):
        """运行抢票程序"""
        self.logger.info("开始运行抢票程序")
        try:
            self.init_driver()
            self.login()
            
            start_time = datetime.now()
            self.logger.info("等待抢票...")
            
            while True:
                if self.select_ticket():
                    if self.select_buyer():
                        if self.submit_order():
                            end_time = datetime.now()
                            duration = (end_time - start_time).total_seconds()
                            self.logger.info(f"抢票成功！耗时：{duration:.2f}秒")
                            break
                        else:
                            self.logger.warning("提交订单失败，重试中...")
                    else:
                        self.logger.warning("选择购票人失败，重试中...")
                else:
                    self.logger.warning("选择门票失败，重试中...")
                
        except Exception as e:
            self.logger.error(f"抢票过程发生错误: {str(e)}")
        finally:
            if self.driver:
                self.driver.quit()
            self.logger.info("抢票程序结束")

if __name__ == "__main__":
    ticket_bot = DamaiTicket()
    ticket_bot.run() 