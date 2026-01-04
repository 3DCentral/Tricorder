from datetime import datetime

from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
from time import sleep
import subprocess
import signal

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

        #all_sprites.add(LcarsMoveToMouse(colours.WHITE), layer=1)
        self.beep1 = Sound("assets/audio/panel/201.wav")
        Sound("assets/audio/panel/220.wav").play()
        
        self.tuned_in = False

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
        if self.emf_gadget.visible and self.emf.scanning:
            self.emf_gadget.image = self.emf.spectrum_image
            #if psutil.pid_exists(self.emf_gadget.pid):
            #self.emf_gadget.image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
        self.myScreen = screenSurface

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
            #self.microscope_gadget_ref.visible = True
            #self.microscope_gadget.visible = False
        if self.spectral_gadget.visible:
            if self.spectro.scanning == False:
                self.spectro.cam.start()
            self.spectro.analyzing = False
            self.spectro.scanning = True
            #self.spectro.image = 
        if self.emf_gadget.visible:
            # TO DO set scanning to true and move this to widgets class .update
            self.emf.scanning = True            
            self.emf_gadget.emf_scanning = True

            # TO DO:  check if pid is still going, otherwise set scanning to false. only initiate scan if previous is done
            # also check what range is selected
            #os.system("python /home/tricorder/rpi_lcars-master/rtl_test.py")
            self.emf.pid = os.system("python /home/tricorder/rpi_lcars-master/rtl_scan_2.py 85e6 105e6 &") 
            self.emf.spectrum_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
            #self.emf_gadget.image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
            
                
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
                #self.fm_pid = os.system("rtl_fm -f 99.9e6 -M wbfm -s 200000 -r 48000 - | play -t raw -r 48k -es -b 16 -c 1 -V1 - &")
                process = subprocess.Popen(['bash', '-c', 'rtl_fm -f ' + str(self.emf_gadget.target_frequency) + 'e6 -M wbfm -s 200000 -r 48000 - | play -t raw -r 48k -es -b 16 -c 1 -V1 - &'], 
                             preexec_fn=os.setsid) 
                self.fm_pid = process.pid
                #os.killpg(os.getpgid(self.fm_pid), signal.SIGTERM)
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
            #self.microscope_gadget.image = pygame.image.load(files[self.micro.reviewing])
            #self.microscope_gadget.image.blit(pygame.image.load(files[self.micro.reviewing]),(854,289))
            review_surf = pygame.Surface((640,480))
            review_surf.blit(pygame.image.load(sorted_files[self.micro.reviewing]),(-299,-187))
            print("file time:" + str(os.path.getmtime(sorted_files[self.micro.reviewing])))
            self.microscope_gadget.image = review_surf
            self.micro.reviewing+=1
        if self.emf_gadget.visible:            
            self.emf.spectrum_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
            

       
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
            #self.microscope_gadget.image = pygame.image.load(files[self.micro.reviewing])
            #self.microscope_gadget.image.blit(pygame.image.load(files[self.micro.reviewing]),(854,289))
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
            #self.microscope_gadget.image = pygame.image.load(files[self.micro.reviewing])
            #self.microscope_gadget.image.blit(pygame.image.load(files[self.micro.reviewing]),(854,289))
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
            #self.microscope_gadget.image = pygame.image.load(files[self.micro.reviewing])
            #self.microscope_gadget.image.blit(pygame.image.load(files[self.micro.reviewing]),(854,289))
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
            #self.microscope_gadget.image = pygame.image.load(files[self.micro.reviewing])
            #self.microscope_gadget.image.blit(pygame.image.load(files[self.micro.reviewing]),(854,289))
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
            
        self.micro.scanning = False
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
        self.microscope_gadget.visible = False
        self.spectral_gadget.visible = False
        self.dashboard.visible = True
        self.weather.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False

    def microscopeHandler(self, item, event, clock):
    
        if self.spectro.scanning == True:
            self.spectro.cam.stop()
        self.spectro.scanning = False
            
        if self.micro.scanning == False:
            self.micro.cam.start()
        self.micro.scanning = True
        self.micro.reviewing = 0
        self.hideInfoText()
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
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
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
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
        self.emf_gadget.visible = True
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
        if self.spectro.scanning == False and self.spectro.analyzing == False:
            self.spectro.cam.start()
        self.spectro.scanning = True
        self.spectro.analyzing = False
        self.spectral_gadget.visible = True
        self.emf_gadget.visible = False
        self.emf_gadget.emf_scanning = False
        self.microscope_gadget.visible = False
        self.dashboard.visible = False
        self.weather.visible = False
        self.microscope_gadget_ref.visible = False
        self.dashboard_ref.visible = False
        
    def logoutHandler(self, item, event, clock):
        from screens.authorize import ScreenAuthorize
        self.loadScreen(ScreenAuthorize())

