#!/usr/bin/env python3
# Copyright 2017 loblab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from datetime import date
from datetime import timedelta
import time
import sys
import os
import re
import base64
import subprocess

class Logger:
    def __init__(self, level):
        self.level = 0 if level is None else level

    def log(self, msg, level=None):
        self.time_string_formatter = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(time.time()))
        self.level = self.level if level is None else level
        if self.level > 0:
            print("[" + self.time_string_formatter + "] - " + msg)


class Robot:

    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:64.0) Gecko/20100101 Firefox/64.0"
    LOGIN_URL = "https://www.noip.com/login"
    HOST_URL = "https://my.noip.com/#!/dynamic-dns"
    DNS_RECORDS_URL = "https://www.noip.com/members/dns/"

    def __init__(self, username, password, debug):
        self.debug = debug
        self.username = username
        self.password = password
        self.browser = self.init_browser()
        self.logger = Logger(debug)

    @staticmethod
    def init_browser():
        options = webdriver.ChromeOptions()
        #added for Raspbian Buster 4.0+ versions. Check https://www.raspberrypi.org/forums/viewtopic.php?t=258019 for reference.
        options.add_argument("disable-features=VizDisplayCompositor")
        options.add_argument("headless")
        options.add_argument("no-sandbox")  # need when run in docker
        options.add_argument("window-size=1200x800")
        options.add_argument("user-agent=" + Robot.USER_AGENT)
        if 'https_proxy' in os.environ:
            options.add_argument("proxy-server=" + os.environ['https_proxy'])
        browser = webdriver.Chrome(options=options)
        browser.set_page_load_timeout(90) # Extended timeout for Raspberry Pi.
        return browser

    def login(self):
        self.logger.log("Opening " + Robot.LOGIN_URL + "...")
        self.browser.get(Robot.LOGIN_URL)
        if self.debug > 1:
            self.browser.save_screenshot("debug1.png")

        self.logger.log("Logging in...")
        ele_usr = self.browser.find_element(by=By.XPATH, value="//form[@id='clogs']//input[@name='username']")
        ele_pwd = self.browser.find_element(by=By.XPATH, value="//form[@id='clogs']//input[@name='password']")
        ele_usr.send_keys(self.username)
        ele_pwd.send_keys(base64.b64decode(self.password).decode('utf-8'))
        self.browser.find_element(by=By.XPATH, value="//form[@id='clogs']/button[@type='submit']").click()
        if self.debug > 1:
            time.sleep(1)
            self.browser.save_screenshot("debug2.png")

    def update_hosts(self):
        count = 0

        self.open_dns_records_page()
        time.sleep(1)
        host_names = []

        hosts = self.get_hosts()
        for host in hosts:
            host_names.append(host.text)
        for host_name in host_names:
            self.open_dns_records_page()
            time.sleep(1)
            host_button = self.get_host_button(host_name)
            self.update_host(host_button, host_name)
            count += 1
        self.open_hosts_page()
        time.sleep(3)
        self.browser.save_screenshot("results.png")
        self.logger.log("Confirmed hosts: " + str(count), 2)

        iteration = 0
        next_renewal = []
        for host_name in host_names:
            expiration_days = self.get_host_expiration_days(host_name, iteration)
            next_renewal.append(expiration_days)
            iteration += 1
        nr = min(next_renewal) - 6
        today = date.today() + timedelta(days=nr)
        day = str(today.day)
        month = str(today.month)
        subprocess.call(['/usr/local/bin/noip-renew-skd.sh', day, month, "True"])
        return True

    def open_hosts_page(self):
        self.logger.log("Opening " + Robot.HOST_URL + "...")
        try:
            self.browser.get(Robot.HOST_URL)
        except TimeoutException as e:
            self.browser.save_screenshot("timeout.png")
            self.logger.log("Timeout: " + str(e))

    def open_dns_records_page(self):
        self.logger.log("Opening " + Robot.DNS_RECORDS_URL + "...")
        try:
            self.browser.get(Robot.DNS_RECORDS_URL)
        except TimeoutException as e:
            self.browser.save_screenshot("timeout.png")
            self.logger.log("Timeout: " + str(e))

    def update_host(self, host_button, host_name):
        self.logger.log("Updating " + host_name)
        host_button.click()
        time.sleep(3)
        self.browser.find_element(by=By.XPATH, value="//input[@value='Update Hostname']").click()
        time.sleep(1)
        self.browser.save_screenshot(host_name + "_success.png")

    def get_host_expiration_days(self, host_name, iteration):
        try:
            host_a = self.browser.find_element(by=By.XPATH, value="//a[contains(text(), '" + host_name + "')]")
            host = host_a.find_element(by=By.XPATH, value=".//parent::td[@data-title='Host']")
            host_remaining_days = host.find_element(by=By.XPATH, value=".//a[contains(@class,'no-link-style')]").text
        except:
            host_remaining_days = "Expires in 7 days"
            pass
        regex_match = re.search("\\d+", host_remaining_days)
        if regex_match is None:
            raise Exception("Expiration days label does not match the expected pattern in iteration: " + str(iteration))
        expiration_days = int(regex_match.group(0))
        return expiration_days

    def get_host_button(self, host_name):
        host_td = self.browser.find_element(by=By.XPATH, value="//td[contains(text(), '" + host_name + "')]")
        return host_td.find_element(by=By.XPATH, value=".//following-sibling::td/a[contains(text(), 'Modify')]")

    def get_hosts(self):
        host_tds = self.browser.find_elements(by=By.XPATH, value="//td[@scope='row'][contains(@class, 'overflow-wrap')]")
        if len(host_tds) == 0:
            raise Exception("No hosts or host table rows not found")
        return host_tds

    def run(self):
        rc = 0
        self.logger.log("Debug level: " + str(self.debug))
        try:
            self.login()
            time.sleep(1)
            if not self.update_hosts():
                rc = 3
        except Exception as e:
            self.logger.log(str(e))
            self.browser.save_screenshot("exception.png")
            subprocess.call(['/usr/local/bin/noip-renew-skd.sh', "*", "*", "False"])
            rc = 2
        finally:
            self.browser.quit()
        return rc


def main(argv=None):
    noip_username, noip_password, debug,  = get_args_values(argv)
    return (Robot(noip_username, noip_password, debug)).run()


def get_args_values(argv):
    if argv is None:
        argv = sys.argv
    if len(argv) < 3:
        print("Usage: " + argv[0] + " <noip_username> <noip_password> [<debug-level>] ")
        sys.exit(1)

    noip_username = argv[1]
    noip_password = argv[2]
    debug = 1
    if len(argv) > 3:
        debug = int(argv[3])
    return noip_username, noip_password, debug


if __name__ == "__main__":
    sys.exit(main())
