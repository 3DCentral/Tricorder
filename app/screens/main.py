from datetime import datetime

from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.waterfall import LcarsWaterfall
from ui.widgets.screen import LcarsScreen
from time import sleep
import subprocess
import signal
import os
import glob


from datasources.network import get_ip_address_string


class ScreenMain(LcarsScreen):
    def setup(self, all_sprites):
        all_sprites.add(LcarsBackgroundImage("assets/lcars_screen_i5.png"),
                        layer=0)

        # panel text
        all_sprites.add(LcarsText(colours.BLACK, (15, 44), "LCARS 105"),
                        layer=1)
                        
        #all_sprites.add(LcarsText(colours.ORANGE, (0, 48), "TRICORDER", 2),
        #                layer=1)
        all_sprites.add(LcarsBlockMedium(colours.RED_BROWN, (186, 5), "SCAN", self.scanHandler),
                        layer=1)
        all_sprites.add(LcarsBlockSmall(colours.ORANGE, (357, 5), "RECORD", self.recordHandler),
                        layer=1)
        all_sprites.add(LcarsBlockLarge(colours.BEIGE, (463, 5), "ANALYZE", self.analyzeHandler),
                        layer=1)

        self.ip_address = LcarsText(colours.BLACK, (444, 520),
                                    get_ip_address_string())
        all_sprites.add(self.ip_address, layer=1)

        # info text
        all_sprites.add(LcarsText(colours.WHITE, (192, 223), "EVENT LOG:", 1.5),
                        layer=3)
        all_sprites.add(LcarsText(colours.BLUE, (244, 223), "2 ALARM ZONES TRIGGERED", 1.5),
                        layer=3)
        all_sprites.add(LcarsText(colours.BLUE, (286, 223), "14.3 kWh USED YESTERDAY", 1.5),
                        layer=3)
        all_sprites.add(LcarsText(colours.BLUE, (330, 223), "1.3 Tb DATA USED THIS MONTH", 1.5),
                        layer=3)
        self.info_text = all_sprites.get_sprites_from_layer(3)
        self.hideInfoText()

        # date display
        self.stardate = LcarsText(colours.BLUE, (12, 888), "STAR DATE", 1.5)
        self.lastClockUpdate = 0
        all_sprites.add(self.stardate, layer=1)

        # buttons
        all_sprites.add(LcarsBlockTop(colours.PEACH, (72, 248), "ATMOSPHERIC", self.weatherHandler),
                        layer=4)
                        
        self.micro = LcarsMicro(colours.BEIGE, (76, 778), "MICROSCOPE", self.microscopeHandler)
        self.micro.scanning = False
        all_sprites.add(self.micro,
                        layer=4)
        all_sprites.add(LcarsButton(colours.RED_BROWN, (6, 1142), "LOGOUT", self.logoutHandler),
                        layer=4)
        all_sprites.add(LcarsBlockTop(colours.PURPLE, (72, 417), "GEOSPATIAL", self.gaugesHandler),
                        layer=4)
        self.emf = LcarsEMF(colours.PEACH, (72, 587), "EMF", self.emfHandler)
        all_sprites.add(self.emf,
                        layer=4)
        self.emf.scanning = False
        self.spectro = LcarsSpectro(colours.BLUE, (76, 935), "SPECTRAL", self.spectralHandler)
        self.spectro.scanning = False
        self.spectro.analyzing = False
        all_sprites.add(self.spectro,
                        layer=4)
                        
        # D pad for nagivation
        all_sprites.add(LcarsNav(colours.BLUE,(492,1125),"^", self.navHandlerUp), layer=4)
        all_sprites.add(LcarsNav(colours.BLUE,(634,1125),"v", self.navHandlerDown), layer=4)
        all_sprites.add(LcarsNav(colours.BLUE,(560,1055),"<", self.navHandlerLeft), layer=4)
        all_sprites.add(LcarsNav(colours.BLUE,(560,1194),">", self.navHandlerRight), layer=4)

        # gadgets
        all_sprites.add(LcarsGifImage("assets/gadgets/fwscan.gif", (356, 1058), 100), layer=1)

        # microscope gadget
        self.microscope_gadget = LcarsImage("assets/micro.png", (187, 299))
        self.microscope_gadget_ref = LcarsImage("assets/micro_ref.png", (187, 299))
        self.microscope_gadget.visible = False
        self.microscope_gadget_ref.visible = False
        all_sprites.add(self.microscope_gadget, layer=2)
        all_sprites.add(self.microscope_gadget_ref, layer=2)

        self.dashboard = LcarsImage("assets/geo.png", (187, 299))
        self.dashboard_ref = LcarsImage("assets/geo_ref.png", (187, 299))
        self.dashboard.visible = False
        self.dashboard_ref.visible = False
        all_sprites.add(self.dashboard, layer=2)
        all_sprites.add(self.dashboard_ref, layer=2)

        self.weather = LcarsImage("assets/atmosph.png", (187, 299))
        self.weather.visible = False
        all_sprites.add(self.weather, layer=2)
        
        self.emf_gadget = LcarsImage("assets/emf.png", (187, 299))
        self.emf_gadget.visible = False
        all_sprites.add(self.emf_gadget, layer=2)
        
        self.spectral_gadget = LcarsImage("assets/spectral.png", (187, 299))
        self.spectral_gadget.visible = False
        all_sprites.add(self.spectral_gadget, layer=2)
        
        # Waterfall display for live scanning
        self.waterfall_display = LcarsWaterfall((187, 299), (640, 480))
        self.waterfall_display.visible = False
        all_sprites.add(self.waterfall_display, layer=2)


        #all_sprites.add(LcarsMoveToMouse(colours.WHITE), layer=1)
        self.beep1 = Sound("assets/audio/panel/201.wav")
        Sound("assets/audio/panel/220.wav").play()
        
        self.tuned_in = False
        
        # Initialize spectrum checking throttle
        self.last_spectrum_check = 0
        
        # Scanning animation state
        self.scan_animation_frame = 0
        self.last_animation_update = 0


        # Live scan state
        self.live_scan_process = None
        self.live_scan_active = False
        self.last_waterfall_check = 0

    def update(self, screenSurface, fpsClock):
        if pygame.time.get_ticks() - self.lastClockUpdate > 1000:
            #self.stardate.setText("STAR DATE {}".format(datetime.now().strftime("%d%m.%y %H:%M:%S")))
            hour_formatted = int(int(format(datetime.now().strftime("%H"))) / 24 * 10)
            self.stardate.setText("STAR DATE {}".format(datetime.now().strftime("%y%m%d.")) + str(hour_formatted))
            self.lastClockUpdate = pygame.time.get_ticks()
        LcarsScreen.update(self, screenSurface, fpsClock)
        if self.microscope_gadget.visible and self.micro.scanning:
            self.microscope_gadget.image = self.micro.micro_image
        if self.spectral_gadget.visible and (self.spectro.scanning or self.spectro.analyzing):
            self.spectral_gadget.image = self.spectro.micro_image
        
        # LIVE EMF SPECTRUM UPDATES
        if self.emf_gadget.visible and self.emf.scanning:
            current_time = pygame.time.get_ticks()
            
            # Check if scan process is still running
            if hasattr(self.emf, 'scan_process'):
                poll_result = self.emf.scan_process.poll()
                if poll_result is not None:
                    # Process has finished
                    print("Scan process completed with code: {}".format(poll_result))
                    self.emf.scanning = False
                    self.emf_gadget.emf_scanning = False
                    # Load the final spectrum image
                    try:
                        self.emf.spectrum_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
                        self.emf_gadget.image = self.emf.spectrum_image
                    except:
                        pass
            
            # Update scanning animation only if still scanning
            if self.emf.scanning:
                if current_time - self.last_animation_update > 200:  # Update every 200ms
                    self.last_animation_update = current_time
                    self.scan_animation_frame = (self.scan_animation_frame + 1) % 4
                
                # Only check for new spectrum files every 500ms to reduce disk I/O
                if current_time - self.last_spectrum_check > 500:
                    self.last_spectrum_check = current_time
                    try:
                        # Find all progress files
                        progress_files = glob.glob("/home/tricorder/rpi_lcars-master/spectrum_progress_*.png")
                        
                        if progress_files:
                            # Get the most recent one
                            latest_file = max(progress_files, key=os.path.getmtime)
                            
                            # Only reload if it's a new file
                            if not hasattr(self.emf, 'last_spectrum_file') or latest_file != self.emf.last_spectrum_file:
                                # Try to load it
                                new_image = pygame.image.load(latest_file)
                                self.emf.spectrum_image = new_image
                                self.emf_gadget.image = new_image
                                self.emf.last_spectrum_file = latest_file
                                print("Loaded spectrum update: {}".format(latest_file))
                        else:
                            # Fallback to main spectrum.png if no progress files exist yet
                            if os.path.exists("/home/tricorder/rpi_lcars-master/spectrum.png"):
                                self.emf.spectrum_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
                                self.emf_gadget.image = self.emf.spectrum_image
                                
                    except (pygame.error, IOError, OSError) as e:
                        # File is still being written or other IO issue, skip this frame
                        print("Could not load spectrum image: {}".format(e))
                        pass
                
                # Draw scanning animation overlay
                self._draw_scanning_animation(screenSurface)
        
        # LIVE WATERFALL UPDATES
        if self.waterfall_display.visible and self.live_scan_active:
            # Check for new waterfall data every 100ms
            current_time = pygame.time.get_ticks()
            if current_time - self.last_waterfall_check > 100:
                self.last_waterfall_check = current_time
                try:
                    # Load waterfall data files
                    import numpy as np
                    waterfall_data = np.load("/home/tricorder/rpi_lcars-master/spectrum_live_waterfall.npy")
                    psd_data = np.load("/home/tricorder/rpi_lcars-master/spectrum_live_psd.npy")
                    frequencies = np.load("/home/tricorder/rpi_lcars-master/spectrum_live_frequencies.npy")
                    
                    # Update waterfall display
                    self.waterfall_display.set_data(waterfall_data, psd_data, frequencies)
                    
                except (IOError, OSError):
                    # Files not ready yet, skip this frame
                    pass
        
        self.myScreen = screenSurface
    
    def _draw_scanning_animation(self, screen):
        """Draw a scanning animation indicator above the EMF display"""
        # Animation dots that cycle
        dots = [".", "..", "...", "....", ".....", "......", ".......", "........", "........."]
        scan_text = "....." + dots[self.scan_animation_frame]
        
        # Position above the EMF gadget display area (adjust these coordinates as needed)
        x_pos = 187 + 450  # Center above the display
        y_pos = 299 - 140   # Above the display
        
        # Create font and render text
        font = pygame.font.Font("assets/swiss911.ttf", 20)
        text_surface = font.render(scan_text, True, (255, 255, 0))  # yellow color
        text_rect = text_surface.get_rect(center=(x_pos, y_pos))
        
        # Draw semi-transparent background box
        padding = 10
        bg_rect = pygame.Rect(
            text_rect.x - padding,
            text_rect.y - padding,
            text_rect.width + padding * 2,
            text_rect.height + padding * 2
        )
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height))
        bg_surface.set_alpha(180)
        bg_surface.fill((0, 0, 0))
        screen.blit(bg_surface, bg_rect)
        
        # Draw text
        screen.blit(text_surface, text_rect)

    def handleEvents(self, event, fpsClock):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.beep1.play()

        if event.type == pygame.MOUSEBUTTONUP:
            return False

    def hideInfoText(self):
        if self.info_text[0].visible:
            for sprite in self.info_text:
                sprite.visible = False

    def showInfoText(self):
        for sprite in self.info_text:
            sprite.visible = True
            
    def scanHandler(self, item, event, clock):
        self.hideInfoText()
        if self.dashboard.visible:
            self.dashboard.visible = False
            self.dashboard_ref.visible = True
        if self.microscope_gadget.visible: 
            if self.micro.scanning == False:
                self.micro.cam.start()
            self.micro.scanning = True
        if self.spectral_gadget.visible:
            if self.spectro.scanning == False:
                self.spectro.cam.start()
            self.spectro.analyzing = False
            self.spectro.scanning = True
        if self.emf_gadget.visible:
            self.emf.scanning = True            
            self.emf_gadget.emf_scanning = True
            
            # Reset the last spectrum file tracking so we start fresh
            if hasattr(self.emf, 'last_spectrum_file'):
                delattr(self.emf, 'last_spectrum_file')
            
            # Use subprocess.Popen to get actual process handle
            self.emf.scan_process = subprocess.Popen(
                ['python', '/home/tricorder/rpi_lcars-master/rtl_scan_2.py', '85e6', '105e6'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Try to load initial spectrum if it exists
            try:
                if os.path.exists("/home/tricorder/rpi_lcars-master/spectrum.png"):
                    self.emf.spectrum_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
            except:
                pass
            
                
    def recordHandler(self, item, event, clock):
        self.hideInfoText()
        if self.micro.scanning and self.microscope_gadget.visible:
            filename = "microscope_" + format(datetime.now().strftime("%y.%m.%d.%H.%M.%S")) + ".jpg"
            pygame.image.save(self.myScreen,"/home/tricorder/rpi_lcars-master/app/screenshots/" + filename)
        if self.spectro.scanning and self.spectral_gadget.visible:
            self.spectro.scanning = False
            self.spectro.analyzing = True
            self.spectro.analyze_complete = False
            print("analyzing...")
        if self.emf_gadget.visible:
            if self.tuned_in == True:
                os.killpg(os.getpgid(self.fm_pid), signal.SIGTERM)
                self.tuned_in = False
            else:
                print("try to listen in to: ", self.emf_gadget.target_frequency)
                print("'rtl_fm -f ",str(self.emf_gadget.target_frequency),"e6 -M wbfm -s 200000 -r 48000 - | play -t raw -r 48k -es -b 16 -c 1 -V1 - ")
                process = subprocess.Popen(['bash', '-c', 'rtl_fm -f ' + str(self.emf_gadget.target_frequency) + 'e6 -M wbfm -s 200000 -r 48000 - | play -t raw -r 48k -es -b 16 -c 1 -V1 - &'], 
                             preexec_fn=os.setsid) 
                self.fm_pid = process.pid
                self.tuned_in = True        
        
            
    def analyzeHandler(self, item, event, clock):
        self.hideInfoText() 
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
        if self.microscope_gadget.visible:
            if self.micro.scanning:
                self.micro.cam.stop()
            self.micro.scanning = False
            files = [f for f in glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")]
            sorted_files = sorted( files, key = lambda file: os.path.getmtime(file), reverse=True)
            if self.micro.reviewing >= len(files):
                self.micro.reviewing = 0
            review_surf = pygame.Surface((640,480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]),(-299,-187))
            print("file time:" + str(os.path.getmtime(sorted_files[self.micro.reviewing])))
            self.microscope_gadget.image = review_surf
            self.micro.reviewing+=1
        # Handle EMF gadget - Toggle live scanning mode
        if self.emf_gadget.visible or self.waterfall_display.visible:
            if not self.live_scan_active:
                # Start live scan
                print("Starting live scan at 99.5 MHz...")
                self.live_scan_process = subprocess.Popen(
                    ['python', '/home/tricorder/rpi_lcars-master/rtl_scan_live.py', '99.5e6'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.live_scan_active = True
                
                # Show waterfall display, hide EMF static
                self.emf_gadget.visible = False
                self.waterfall_display.visible = True
            else:
                # Stop live scan but keep waterfall visible (frozen)
                print("Stopping live scan...")
                if self.live_scan_process:
                    self.live_scan_process.terminate()
                    self.live_scan_process.wait()
                    self.live_scan_process = None
                self.live_scan_active = False
                print("Live scan stopped - waterfall frozen")
            
       
    # TO DO: break this out into functions     
    def navHandlerUp(self, item, event, clock):
        self.hideInfoText() 
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
        if self.microscope_gadget.visible:
            if self.micro.scanning:
                self.micro.cam.stop()
            self.micro.scanning = False
            files = [f for f in glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")]
            sorted_files = sorted( files, key = lambda file: os.path.getmtime(file), reverse=True)
            self.micro.reviewing = 0
            review_surf = pygame.Surface((640,480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]),(-299,-187))
            print("file time:" + str(os.path.getmtime(sorted_files[self.micro.reviewing])))
            self.microscope_gadget.image = review_surf
            
    def navHandlerDown(self, item, event, clock):
        self.hideInfoText() 
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
        if self.microscope_gadget.visible:
            if self.micro.scanning:
                self.micro.cam.stop()
            self.micro.scanning = False
            files = [f for f in glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")]
            sorted_files = sorted( files, key = lambda file: os.path.getmtime(file), reverse=True)
            self.micro.reviewing = len(files)-1
            review_surf = pygame.Surface((640,480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]),(-299,-187))
            print("file time:" + str(os.path.getmtime(sorted_files[self.micro.reviewing])))
            self.microscope_gadget.image = review_surf     
                       
    def navHandlerLeft(self, item, event, clock):
        self.hideInfoText() 
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
        if self.microscope_gadget.visible:
            if self.micro.scanning:
                self.micro.cam.stop()
            self.micro.scanning = False
            files = [f for f in glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")]
            sorted_files = sorted( files, key = lambda file: os.path.getmtime(file), reverse=True)
            if self.micro.reviewing >= len(files):
                self.micro.reviewing = 0
            review_surf = pygame.Surface((640,480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]),(-299,-187))
            print("file time:" + str(os.path.getmtime(sorted_files[self.micro.reviewing])))
            self.microscope_gadget.image = review_surf
            self.micro.reviewing+=1
        if self.emf_gadget.emf_scanning:
            print("moving the needle")
            self.emf_gadget.target_frequency-=1
                          
    def navHandlerRight(self, item, event, clock):
        self.hideInfoText() 
        if self.microscope_gadget_ref.visible:
            self.microscope_gadget_ref.visible = False
            self.microscope_gadget.visible = True
        if self.microscope_gadget.visible:
            if self.micro.scanning:
                self.micro.cam.stop()
            self.micro.scanning = False
            files = [f for f in glob.glob("/home/tricorder/rpi_lcars-master/app/screenshots/microscope_*.jpg")]
            sorted_files = sorted( files, key = lambda file: os.path.getmtime(file), reverse=True)
            if self.micro.reviewing >= len(files):
                self.micro.reviewing = 0
            review_surf = pygame.Surface((640,480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]),(-299,-187))
            print("file time:" + str(os.path.getmtime(sorted_files[self.micro.reviewing])))
            self.microscope_gadget.image = review_surf
            self.micro.reviewing-=1
        if self.emf_gadget.emf_scanning:
            self.emf_gadget.target_frequency+=1
            
    # TO DO: put these into an array and iterate over them instead
    def gaugesHandler(self, item, event, clock):
        self.hideInfoText()
        if self.micro.scanning:
            self.micro.cam.stop()
            self.micro.scanning = False
        if self.spectro.scanning:
            self.spectro.cam.stop()
        self.spectro.scanning = False
        
        # Stop live scan if active
        if self.live_scan_active:
            if self.live_scan_process:
                self.live_scan_process.terminate()
                self.live_scan_process.wait()
                self.live_scan_process = None
            self.live_scan_active = False
            
        self.micro.scanning = False
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
        self.microscope_gadget.visible = False
        self.spectral_gadget.visible = False
        self.waterfall_display.visible = False
        self.dashboard.visible = True
        self.weather.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False

    def microscopeHandler(self, item, event, clock):
    
        if self.spectro.scanning == True:
            self.spectro.cam.stop()
        self.spectro.scanning = False
        
        # Stop live scan if active
        if self.live_scan_active:
            if self.live_scan_process:
                self.live_scan_process.terminate()
                self.live_scan_process.wait()
                self.live_scan_process = None
            self.live_scan_active = False
            
        if self.micro.scanning == False:
            self.micro.cam.start()
        self.micro.scanning = True
        self.micro.reviewing = 0
        self.hideInfoText()
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
        self.waterfall_display.visible = False
        self.microscope_gadget.visible = True
        self.dashboard.visible = False
        self.spectral_gadget.visible = False
        self.weather.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False

    def weatherHandler(self, item, event, clock):
        self.hideInfoText()
        if self.micro.scanning:
            self.micro.cam.stop()
        if self.spectro.scanning:
            self.spectro.cam.stop()
        self.spectro.scanning = False
        self.micro.scanning = False
        
        # Stop live scan if active
        if self.live_scan_active:
            if self.live_scan_process:
                self.live_scan_process.terminate()
                self.live_scan_process.wait()
                self.live_scan_process = None
            self.live_scan_active = False
            
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
        self.waterfall_display.visible = False
        self.spectral_gadget.visible = False
        self.microscope_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = True
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False

    def homeHandler(self, item, event, clock):
        self.showInfoText()
        if self.micro.scanning:
            self.micro.cam.stop()
        if self.spectro.scanning:
            self.spectro.cam.stop()
        self.spectro.scanning = False
        self.micro.scanning = False
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
        self.spectral_gadget.visible = False
        self.microscope_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False
        
    def emfHandler(self, item, event, clock):
        self.hideInfoText()
        if self.micro.scanning:
            self.micro.cam.stop()
        if self.spectro.scanning:
            self.spectro.cam.stop()
        self.spectro.scanning = False
        self.micro.scanning = False
        
        # Stop live scan if active and switch back to static EMF view
        if self.live_scan_active:
            if self.live_scan_process:
                self.live_scan_process.terminate()
                self.live_scan_process.wait()
                self.live_scan_process = None
            self.live_scan_active = False
            
        self.emf_gadget.visible = True
        self.waterfall_display.visible = False
        self.spectral_gadget.visible = False
        self.microscope_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False
        
    def spectralHandler(self, item, event, clock):
        self.hideInfoText()
        if self.micro.scanning:
            self.micro.cam.stop()
        self.micro.scanning = False
        
        # Stop live scan if active
        if self.live_scan_active:
            if self.live_scan_process:
                self.live_scan_process.terminate()
                self.live_scan_process.wait()
                self.live_scan_process = None
            self.live_scan_active = False
            
        if self.spectro.scanning == False and self.spectro.analyzing == False:
            self.spectro.cam.start()
        self.spectro.scanning = True
        self.spectro.analyzing = False
        self.spectral_gadget.visible = True
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
        self.waterfall_display.visible = False
        self.microscope_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False
        
    def logoutHandler(self, item, event, clock):
        from screens.authorize import ScreenAuthorize
        self.loadScreen(ScreenAuthorize())
