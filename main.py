from time import sleep
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import argparse
import getpass
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions

def get_browser(browser_name="chrome", headless=True):
    if browser_name.lower() == "chrome" or browser_name.lower() == "brave":
        options = ChromeOptions()
        if browser_name.lower() == "brave":
            options.binary_location = "/usr/bin/brave-browser"
        options.headless = headless
        service = ChromeService("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)

    elif browser_name.lower() == "firefox":
        options = FirefoxOptions()
        options.headless = headless
        service = FirefoxService()
        return webdriver.Firefox(service=service, options=options)

    elif browser_name.lower() == "edge":
        options = EdgeOptions()
        options.headless = headless
        service = EdgeService()
        return webdriver.Edge(service=service, options=options)

    else:
        raise ValueError(f"Unsupported browser: {browser_name}")


class InstaBot:
	def __init__(self, username, password):
		self.browser = get_browser(browser_name=input("Which browser? (chrome/brave/firefox/edge): ").strip(), headless=False)
		self.browser.implicitly_wait(5)
		self.wait = WebDriverWait(self.browser, 30)  # Increased timeout for slow networks

		# Login in to Instagram
		home_page = HomePage(self.browser, self.wait)
		home_page.login(username, password)

		self.username = username

	def unfollow(self):
		# Go to your Instagram profile page
		self.browser.get("https://www.instagram.com/{}/".format(self.username))
		
		# Wait for profile page to load
		try:
			self.wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "followers")))
			print("Profile page loaded successfully.")
		except TimeoutException:
			print("Error: Profile page took too long to load.")
			return

		# Get the usernames of all your followers
		followers, num_of_followers = self.get_followers()
		
		# Check to make sure that approximately all followers were scraped
		if len(followers) < num_of_followers * 0.99:
			print("There's been an error while scraping the usernames of your followers.")
			return

		# Unfollow accounts that aren't following you
		num_of_accounts_unfollowed, accounts_unfollowed = self.compare_to_following_and_unfollow(followers)
		print("You've unfollowed {} accounts.".format(num_of_accounts_unfollowed))
		sleep(2)
		
		# Close browser
		self.browser.quit()

		# Store the usernames of accounts you've unfollowed 
		new_file = open('accounts_unfollowed.txt', 'w')
		for account_unfollowed in accounts_unfollowed:
			new_file.write(account_unfollowed + "\n")
		new_file.close()

		return

	def scroll(self, popup_window):
		"""
		Scroll through popup until all content is loaded.
		Works on both slow and fast networks by checking loading state.
		"""
		js_command = """
					loading = document.querySelector("div[role='progressbar']");
					if (loading) {
						loading.scrollIntoView();
					}
					return loading;
					"""
		
		max_scroll_attempts = 200  # Prevent infinite loops
		scroll_count = 0
		consecutive_no_loading = 0
		
		print("Starting to scroll...")
		
		import time
		start_time = time.time()
		max_scroll_time = 300  # 5 minutes maximum
		
		while scroll_count < max_scroll_attempts:
			# Check if we've exceeded maximum scroll time
			if time.time() - start_time > max_scroll_time:
				print("Warning: Reached maximum scroll time (5 minutes). Stopping scroll.")
				break
			
			loading_el = self.browser.execute_script(js_command)
			
			if loading_el is None:
				consecutive_no_loading += 1
				# Wait to confirm loading is truly done (not just a brief moment)
				if consecutive_no_loading >= 3:
					print("Scrolling complete - all content loaded.")
					break
			else:
				consecutive_no_loading = 0  # Reset counter if we see loading again
				if scroll_count % 10 == 0:  # Progress update every 10 scrolls
					print(f"Still scrolling... ({scroll_count} attempts)")
			
			sleep(1.5)  # Adjusted for better reliability
			scroll_count += 1
		
		if scroll_count >= max_scroll_attempts:
			print("Warning: Reached maximum scroll attempts. Some content may not be loaded.")
		
		# Final wait to ensure everything is rendered
		print("Waiting for final rendering...")
		sleep(2)
		print("Scroll complete.")

	def convert_str_to_num(self, num_as_str):
		num_map = {'K':1000, 'M':1000000, 'B':1000000000}
		num_as_str = num_as_str.replace(",", "")

		last_ch = num_as_str[-1]
		if last_ch in num_map:
			num_as_int = float(num_as_str[:-1])
			num_as_int *= num_map[last_ch]
			num_as_int = int(num_as_int)
		else:
			num_as_int = int(num_as_str)

		return num_as_int

	def get_followers(self):
		# Wait for and get number of followers - try multiple selectors
		print("Looking for followers count...")
		
		followers_selectors = [
			# Try link text first (most reliable)
			(By.XPATH, "//a[contains(@href, '/followers/')]/span/span"),
			(By.XPATH, "//a[contains(@href, '/followers/')]/span"),
			# Try by aria-label or title
			(By.XPATH, "//a[@title='followers']//span"),
			# Original selector
			(By.XPATH, "/html/body/div[2]/div/div/div[2]/div/div/div[1]/div[2]/div/div[1]/section/main/div/header/section[3]/ul/li[2]/div/a/span/span"),
			# More flexible selectors
			(By.XPATH, "//header//ul/li[2]//a/span/span"),
			(By.XPATH, "//section//ul/li[contains(., 'followers')]//span"),
		]
		
		num_of_followers = 0
		for selector in followers_selectors:
			try:
				followers_element = self.wait.until(EC.presence_of_element_located(selector))
				num_of_followers_text = followers_element.text
				if num_of_followers_text:  # Make sure we got text
					num_of_followers = self.convert_str_to_num(num_of_followers_text)
					print(f"Found {num_of_followers} followers.")
					break
			except (TimeoutException, ValueError):
				continue
		
		if num_of_followers == 0:
			print("Error: Could not find followers count with any selector.")
			print("Current URL:", self.browser.current_url)
			print("Please check if you're on your profile page.")
			# Try to manually find it
			try:
				page_source = self.browser.page_source
				if "followers" in page_source.lower():
					print("The word 'followers' is on the page - Instagram layout may have changed.")
			except:
				pass
			return set(), 0

		# Click followers button - try multiple selectors
		followers_button_selectors = [
			(By.PARTIAL_LINK_TEXT, "followers"),
			(By.XPATH, "//a[contains(@href, '/followers/')]"),
			(By.XPATH, "//a[contains(text(), 'followers')]"),
			(By.XPATH, "//header//a[contains(@href, 'followers')]"),
		]
		
		followers_button = None
		for selector in followers_button_selectors:
			try:
				followers_button = self.wait.until(EC.element_to_be_clickable(selector))
				# Scroll into view and use JavaScript click to avoid interception
				self.browser.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", followers_button)
				sleep(1)
				try:
					followers_button.click()
				except:
					# If regular click fails, use JavaScript click
					self.browser.execute_script("arguments[0].click();", followers_button)
				print("Clicked followers button.")
				break
			except TimeoutException:
				continue
		
		if not followers_button:
			print("Error: Could not click followers button.")
			return set(), 0

		# Wait for popup to appear
		try:
			self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.notranslate")))
			print("Followers popup opened.")
		except TimeoutException:
			print("Error: Followers popup did not open.")
			return set(), 0

		# Scroll to load entire list of followers
		self.scroll(followers_button)

		# Get the usernames of all followers
		print("Collecting follower usernames...")
		usernames_of_followers = set()
		
		# Try multiple selectors for username links
		username_selectors = [
			(By.CSS_SELECTOR, "a.notranslate"),
			(By.XPATH, "//div[@role='dialog']//a[contains(@href, '/')]"),
			(By.XPATH, "//span[contains(@class, 'notranslate')]//parent::div//parent::a"),
		]
		
		followers = []
		for selector in username_selectors:
			try:
				followers = self.browser.find_elements(*selector)
				if len(followers) > 0:
					print(f"Found {len(followers)} follower elements using selector.")
					break
			except NoSuchElementException:
				continue
		
		if not followers:
			print("Warning: Could not find any follower elements. Popup structure may have changed.")
		
		for follower in followers:
			try:
				username = follower.text.strip()
				if username and len(username) > 0:  # Only add non-empty usernames
					usernames_of_followers.add(username)
			except:
				continue
		
		print(f"Collected {len(usernames_of_followers)} follower usernames.")
		
		if len(usernames_of_followers) == 0:
			print("WARNING: No follower usernames collected! Check if Instagram's structure changed.")
			print("Attempting to continue anyway...")

		# Close popup window - try multiple selectors
		close_button_selectors = [
			(By.XPATH, "//button[contains(@aria-label, 'Close')]"),
			(By.XPATH, "//div[@role='dialog']//button[contains(@class, 'x1i10hfl')]"),
			(By.XPATH, "/html/body/div[6]/div[2]/div/div/div[1]/div/div[2]/div/div/div/div/div[2]/div/div/div[1]/div/div[3]/div/button"),
			(By.CSS_SELECTOR, "svg[aria-label='Close']"),
			(By.XPATH, "//button[.//*[local-name()='svg' and @aria-label='Close']]"),
		]
		
		popup_closed = False
		for selector in close_button_selectors:
			try:
				close_popup_button = self.wait.until(EC.element_to_be_clickable(selector))
				try:
					close_popup_button.click()
				except:
					self.browser.execute_script("arguments[0].click();", close_popup_button)
				sleep(1)
				print("Closed followers popup.")
				popup_closed = True
				break
			except TimeoutException:
				continue
		
		if not popup_closed:
			print("Warning: Could not find close button. Pressing ESC key...")
			from selenium.webdriver.common.action_chains import ActionChains
			ActionChains(self.browser).send_keys(Keys.ESCAPE).perform()
			sleep(1)

		return usernames_of_followers, num_of_followers

	def compare_to_following_and_unfollow(self, followers):
		# Get number of accounts you are following - try multiple selectors
		print("Looking for following count...")
		
		following_selectors = [
			# Try link text first (most reliable)
			(By.XPATH, "//a[contains(@href, '/following/')]/span/span"),
			(By.XPATH, "//a[contains(@href, '/following/')]/span"),
			# Try by aria-label or title
			(By.XPATH, "//a[@title='following']//span"),
			# Original selector
			(By.XPATH, "/html/body/div[2]/div/div/div[2]/div/div/div[1]/div[2]/div/div[1]/section/main/div/header/section[3]/ul/li[3]/div/a/span/span"),
			# More flexible selectors
			(By.XPATH, "//header//ul/li[3]//a/span/span"),
			(By.XPATH, "//section//ul/li[contains(., 'following')]//span"),
		]
		
		num_following_before = 0
		for selector in following_selectors:
			try:
				following_element = self.wait.until(EC.presence_of_element_located(selector))
				num_following_text = following_element.text
				if num_following_text:  # Make sure we got text
					num_following_before = self.convert_str_to_num(num_following_text)
					print(f"Currently following {num_following_before} accounts.")
					break
			except (TimeoutException, ValueError):
				continue
		
		if num_following_before == 0:
			print("Error: Could not find following count.")
			return 0, set()

		# Click on the "following" button - try multiple selectors
		following_button_selectors = [
			(By.PARTIAL_LINK_TEXT, "following"),
			(By.XPATH, "//a[contains(@href, '/following/')]"),
			(By.XPATH, "//a[contains(text(), 'following')]"),
			(By.XPATH, "//header//a[contains(@href, 'following')]"),
		]
		
		following_button = None
		for selector in following_button_selectors:
			try:
				following_button = self.wait.until(EC.element_to_be_clickable(selector))
				# Scroll into view and use JavaScript click to avoid interception
				self.browser.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", following_button)
				sleep(1)
				try:
					following_button.click()
				except:
					# If regular click fails, use JavaScript click
					self.browser.execute_script("arguments[0].click();", following_button)
				print("Clicked following button.")
				break
			except TimeoutException:
				continue
		
		if not following_button:
			print("Error: Could not click following button.")
			return 0, set()

		# Wait for popup to appear
		try:
			self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.notranslate")))
			print("Following popup opened.")
		except TimeoutException:
			print("Error: Following popup did not open.")
			return 0, set()

		# Scroll to load entire list of users you're following 
		self.scroll(following_button)

		# Unfollow accounts that don't follow you back
		accounts_unfollowed = self.unfollow_helper(followers, num_following_before)

		# Close popup window - try multiple selectors
		close_button_selectors = [
			(By.XPATH, "//button[contains(@aria-label, 'Close')]"),
			(By.XPATH, "//div[@role='dialog']//button[contains(@class, 'x1i10hfl')]"),
			(By.XPATH, "/html/body/div[6]/div[2]/div/div/div[1]/div/div[2]/div/div/div/div/div[2]/div/div/div[1]/div/div[3]/div/button"),
			(By.CSS_SELECTOR, "svg[aria-label='Close']"),
			(By.XPATH, "//button[.//*[local-name()='svg' and @aria-label='Close']]"),
		]
		
		popup_closed = False
		for selector in close_button_selectors:
			try:
				close_popup_button = self.wait.until(EC.element_to_be_clickable(selector))
				try:
					close_popup_button.click()
				except:
					self.browser.execute_script("arguments[0].click();", close_popup_button)
				sleep(2)
				print("Closed following popup.")
				popup_closed = True
				break
			except TimeoutException:
				continue
		
		if not popup_closed:
			print("Warning: Could not find close button. Pressing ESC key...")
			from selenium.webdriver.common.action_chains import ActionChains
			ActionChains(self.browser).send_keys(Keys.ESCAPE).perform()
			sleep(2)

		# Get number of accounts you are following now
		num_following_after = 0
		for selector in following_selectors:
			try:
				following_element = self.wait.until(EC.presence_of_element_located(selector))
				num_following_text = following_element.text
				if num_following_text:
					num_following_after = self.convert_str_to_num(num_following_text)
					print(f"Now following {num_following_after} accounts.")
					break
			except (TimeoutException, ValueError):
				continue
		
		if num_following_after == 0:
			print("Warning: Could not get updated following count.")
			num_following_after = num_following_before - len(accounts_unfollowed)

		# Return the number of people you've unfollowed and their usernames
		num_of_accounts_unfollowed = num_following_before - num_following_after
		return num_of_accounts_unfollowed, accounts_unfollowed

	def unfollow_helper(self, followers, num_following_before):
		accounts_unfollowed = set()
		unfollow_wait = WebDriverWait(self.browser, 10)
		
		print(f"Starting to unfollow accounts that don't follow you back...")
		print(f"Total accounts following: {num_following_before}")
		print(f"Total followers: {len(followers)}")
		
		# First, let's debug what buttons we can find
		print("\n=== DEBUG: Looking for buttons ===")
		all_buttons = self.browser.find_elements(By.TAG_NAME, "button")
		print(f"Total buttons on page: {len(all_buttons)}")
		
		# Try different button text variations
		button_texts = ["Following", "Follow", "Requested"]
		for text in button_texts:
			btns = self.browser.find_elements(By.XPATH, f"//button[contains(text(), '{text}')]")
			print(f"Buttons with '{text}': {len(btns)}")
		
		# Try to find buttons in dialog
		dialog_buttons = self.browser.find_elements(By.XPATH, "//div[@role='dialog']//button")
		print(f"Buttons in dialog: {len(dialog_buttons)}")
		
		# Get all "Following" buttons dynamically
		max_attempts = int(num_following_before) + 10
		attempts = 0
		no_button_count = 0
		
		while attempts < max_attempts:
			try:
				# Try multiple selectors for "Following" buttons
				following_buttons = []
				button_selectors = [
					"//div[@role='dialog']//button[contains(text(), 'Following')]",
					"//button[contains(text(), 'Following')]",
					"//div[@role='dialog']//button[contains(., 'Following')]",
					"//button[@type='button' and contains(., 'Following')]",
				]
				
				for selector in button_selectors:
					following_buttons = self.browser.find_elements(By.XPATH, selector)
					if len(following_buttons) > 0:
						break
				
				if len(following_buttons) == 0:
					no_button_count += 1
					if no_button_count >= 3:
						print("No 'Following' buttons found after 3 attempts. All done or button text may have changed.")
						break
					print(f"No buttons found, attempt {no_button_count}/3...")
					sleep(2)
					attempts += 1
					continue
				
				no_button_count = 0  # Reset counter
				print(f"\nFound {len(following_buttons)} 'Following' buttons in current view...")
				
				# Process the first button
				for button in following_buttons:
					try:
						# Get the username - try multiple approaches
						username = None
						
						# Method 1: Find username in same parent container
						try:
							parent = button
							for level in range(10):  # Go up more levels
								parent = parent.find_element(By.XPATH, "./..")
								try:
									# Try different username selectors
									username_elements = parent.find_elements(By.CSS_SELECTOR, "a.notranslate")
									if not username_elements:
										username_elements = parent.find_elements(By.XPATH, ".//a[contains(@href, '/')]")
									
									for elem in username_elements:
										text = elem.text.strip()
										if text and len(text) > 0 and not text.startswith('#'):
											username = text
											break
									
									if username:
										break
								except:
									continue
						except Exception as e:
							print(f"Method 1 failed: {e}")
						
						# Method 2: Find the nearest link before the button
						if not username:
							try:
								# Get all links in the dialog
								all_links = self.browser.find_elements(By.XPATH, "//div[@role='dialog']//a[contains(@href, '/') and not(contains(@href, 'followers')) and not(contains(@href, 'following'))]")
								# Find the button's position
								button_location = button.location
								# Find closest link above the button
								for link in all_links:
									link_location = link.location
									if abs(link_location['y'] - button_location['y']) < 50:  # Within 50px vertically
										username = link.text.strip()
										if username:
											break
							except Exception as e:
								print(f"Method 2 failed: {e}")
						
						if not username:
							print("Warning: Could not find username, skipping this button...")
							continue
						
						print(f"Found username: {username}")
						
						# Check if this user follows you back
						if username in followers:
							print(f"  → Skipping {username} (follows you back)")
							continue
						
						print(f"  → {username} doesn't follow back, unfollowing...")
						
						# Scroll button into view and click
						self.browser.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", button)
						sleep(0.5)
						
						try:
							button.click()
						except:
							self.browser.execute_script("arguments[0].click();", button)
						
						print("  → Clicked 'Following' button, waiting for confirmation dialog...")
						sleep(1.5)
						
						# Click unfollow confirmation
						unfollow_confirm_selectors = [
							"//button[contains(text(), 'Unfollow') and not(contains(text(), 'Following'))]",
							"//div[@role='dialog'][2]//button[contains(text(), 'Unfollow')]",
							"/html/body/div[7]/div[1]/div/div[2]/div/div/div/div/div/div/button[1]",
							"/html/body/div[8]/div[1]/div/div[2]/div/div/div/div/div/div/button[1]",
							"//button[text()='Unfollow']",
						]
						
						unfollow_confirmed = False
						for conf_selector in unfollow_confirm_selectors:
							try:
								unfollow_button = unfollow_wait.until(
									EC.element_to_be_clickable((By.XPATH, conf_selector))
								)
								print(f"  → Found unfollow confirmation button")
								self.browser.execute_script("arguments[0].click();", unfollow_button)
								unfollow_confirmed = True
								break
							except TimeoutException:
								continue
						
						if unfollow_confirmed:
							accounts_unfollowed.add(username)
							print(f"  ✓ Successfully unfollowed: {username} (Total: {len(accounts_unfollowed)})")
							sleep(2)  # Rate limiting
						else:
							print(f"  ✗ Could not find unfollow confirmation for {username}")
							# Press ESC to close any dialog
							from selenium.webdriver.common.action_chains import ActionChains
							ActionChains(self.browser).send_keys(Keys.ESCAPE).perform()
							sleep(1)
						
						# Only process one button per iteration
						break
						
					except Exception as e:
						print(f"Warning: Error processing button: {e}")
						import traceback
						traceback.print_exc()
						continue
				
				attempts += 1
				sleep(1)
				
			except Exception as e:
				print(f"Warning: Error in main loop: {e}")
				import traceback
				traceback.print_exc()
				attempts += 1
				continue
		
		print(f"\n{'='*50}")
		print(f"Finished unfollowing!")
		print(f"Total unfollowed: {len(accounts_unfollowed)}")
		print(f"{'='*50}")
		return accounts_unfollowed


class HomePage:
	def __init__(self, browser, wait):
		self.browser = browser
		self.wait = wait
		self.browser.get("https://www.instagram.com/")

	def login(self, username, password):
		# Wait for login page to load - try multiple selectors for different Instagram layouts
		print("Waiting for login page to load...")
		
		username_input = None
		password_input = None
		
		# Try different login form selectors (Instagram has multiple layouts)
		username_selectors = [
			(By.CSS_SELECTOR, "input[name='username']"),
			(By.XPATH, "//input[@aria-label='Phone number, username, or email']"),
			(By.XPATH, "//input[@placeholder='Phone number, username, or email']"),
			(By.XPATH, "//input[@type='text' and contains(@class, 'input')]"),
		]
		
		password_selectors = [
			(By.CSS_SELECTOR, "input[name='password']"),
			(By.XPATH, "//input[@aria-label='Password']"),
			(By.XPATH, "//input[@type='password']"),
		]
		
		# Try to find username input
		for selector in username_selectors:
			try:
				username_input = self.wait.until(EC.presence_of_element_located(selector))
				print("Found username input field.")
				break
			except TimeoutException:
				continue
		
		if not username_input:
			print("Error: Could not find username input field on login page.")
			print(f"Current URL: {self.browser.current_url}")
			return
		
		# Try to find password input
		for selector in password_selectors:
			try:
				password_input = self.browser.find_element(*selector)
				print("Found password input field.")
				break
			except NoSuchElementException:
				continue
		
		if not password_input:
			print("Error: Could not find password input field on login page.")
			return
		
		print("Login page loaded successfully.")
		
		# Type your username and password in their respective inputs
		username_input.clear()
		username_input.send_keys(username)
		sleep(0.5)
		password_input.clear()
		password_input.send_keys(password)
		sleep(0.5)

		# Submit credentials - try multiple button selectors
		login_button_selectors = [
			(By.XPATH, "//button[@type='submit']"),
			(By.XPATH, "//button[contains(text(), 'Log in') or contains(text(), 'Log In')]"),
			(By.CSS_SELECTOR, "button[type='submit']"),
			(By.XPATH, "//div[@role='button' and contains(text(), 'Log in')]"),
		]
		
		login_button = None
		for selector in login_button_selectors:
			try:
				login_button = self.browser.find_element(*selector)
				print("Found login button.")
				break
			except NoSuchElementException:
				continue
		
		if not login_button:
			print("Error: Could not find login button. Trying to submit with Enter key...")
			password_input.send_keys(Keys.RETURN)
		else:
			login_button.click()
		
		print("Logging in...")

		# Wait for successful login by checking multiple indicators
		print("Waiting for login to complete...")
		
		# Give Instagram time to process login (don't check too early)
		sleep(3)
		
		# Wait for home page to fully load - check for search box or home navigation
		login_successful = False
		
		# Try multiple indicators of successful login with longer timeout
		indicators = [
			(By.XPATH, "//input[@aria-label='Search input' or @placeholder='Search']"),  # Search box
			(By.XPATH, "//svg[@aria-label='Home']"),  # Home icon
			(By.XPATH, "//a[contains(@href, '/direct/')]"),  # Messages link
			(By.XPATH, "//span[text()='Search']"),  # Search text
			(By.XPATH, "//a[@href='/']"),  # Home link
			(By.CSS_SELECTOR, "svg[aria-label='Home']"),  # Home icon CSS
			(By.CSS_SELECTOR, "a[href*='direct']"),  # Messages link CSS
		]
		
		wait_long = WebDriverWait(self.browser, 45)  # Longer timeout for login
		
		for locator in indicators:
			try:
				element = wait_long.until(EC.presence_of_element_located(locator))
				print("Login successful! Home page loaded.")
				login_successful = True
				break
			except TimeoutException:
				continue
		
		if not login_successful:
			# Check current URL - if we're not on login page, we're probably logged in
			current_url = self.browser.current_url
			print(f"Current URL: {current_url}")
			
			# If URL doesn't contain 'accounts/login', we're likely logged in
			if 'accounts/login' not in current_url:
				print("Login appears successful (not on login page anymore)")
				login_successful = True
			else:
				# Check if we're stuck on verification or error page
				try:
					error_msg = self.browser.find_element(By.XPATH, "//*[contains(text(), 'incorrect') or contains(text(), 'wrong')]")
					print("ERROR: Login failed - incorrect credentials")
					return
				except NoSuchElementException:
					pass
				
				print("Warning: Could not confirm successful login.")
				print("If you can see the Instagram home page in the browser, login was successful.")
				print("Waiting 10 seconds for page to fully load...")
				sleep(10)
				
				# Ask user if they can see they're logged in
				user_input = input("Can you see the Instagram home page? (yes/no): ").strip().lower()
				if user_input in ['yes', 'y']:
					print("Proceeding with the assumption that login was successful...")
					login_successful = True
				else:
					print("Login may have failed. Please check the browser window.")
					return
		
		# Additional wait to ensure all elements are loaded
		sleep(3)
		
		# Handle "Save Your Login Info" popup if it appears
		try:
			not_now_button = self.browser.find_element(By.XPATH, "//button[contains(text(), 'Not now') or contains(text(), 'Not Now')]")
			not_now_button.click()
			print("Dismissed 'Save Login Info' popup.")
			sleep(2)
		except NoSuchElementException:
			pass
		
		# Handle "Turn on Notifications" popup if it appears
		try:
			not_now_button = self.browser.find_element(By.XPATH, "//button[contains(text(), 'Not Now') or contains(text(), 'Not now')]")
			not_now_button.click()
			print("Dismissed 'Notifications' popup.")
			sleep(2)
		except NoSuchElementException:
			pass


def parse_args():
	parser = argparse.ArgumentParser(description="Instagram Bot - Unfollow users who don't follow back")
	parser.add_argument("--username", "-u", required=True,
						help="Instagram username (required)")
	parser.add_argument("--password", "-p", required=True,
						help="Instagram password (required)")
	return parser.parse_args()


if __name__ == "__main__":
	args = parse_args()
	
	try:
		my_insta_bot = InstaBot(args.username, args.password)
		my_insta_bot.unfollow()
	except Exception as e:
		print(f"An error occurred: {e}")
		import traceback
		traceback.print_exc()