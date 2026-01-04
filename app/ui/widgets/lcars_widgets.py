import pygame
import os
from pygame.font import Font
from pygame.locals import *
from scipy import signal
import numpy as np
import colorsys

from ui.utils.sound import Sound
from ui.widgets.sprite import LcarsWidget
from ui import colours

class LcarsElbow(LcarsWidget):
    """The LCARS corner elbow - not currently used"""
    
    STYLE_BOTTOM_LEFT = 0
    STYLE_TOP_LEFT = 1
    STYLE_BOTTOM_RIGHT = 2
    STYLE_TOP_RIGHT = 3
    
    def __init__(self, colour, style, pos, handler=None):
        image = pygame.image.load("assets/elbow.png").convert_alpha()
        # alpha=255
        # image.fill((255, 255, 255, alpha), None, pygame.BLEND_RGBA_MULT)
        if (style == LcarsElbow.STYLE_BOTTOM_LEFT):
            image = pygame.transform.flip(image, False, True)
        elif (style == LcarsElbow.STYLE_BOTTOM_RIGHT):
            image = pygame.transform.rotate(image, 180)
        elif (style == LcarsElbow.STYLE_TOP_RIGHT):
            image = pygame.transform.flip(image, True, False)
        
        self.image = image
        size = (image.get_rect().width, image.get_rect().height)
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.applyColour(colour)

class LcarsTab(LcarsWidget):
    """Tab widget (like radio button) - not currently used nor implemented"""

    STYLE_LEFT = 1
    STYLE_RIGHT = 2
    
    def __init__(self, colour, style, pos, handler=None):
        image = pygame.image.load("assets/tab.png").convert()
        if (style == LcarsTab.STYLE_RIGHT):
            image = pygame.transform.flip(image, False, True)
        
        size = (image.get_rect().width, image.get_rect().height)
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.image = image
        self.applyColour(colour)

class LcarsButton(LcarsWidget):
    """Button - either rounded or rectangular if rectSize is spcified"""

    def __init__(self, colour, pos, text, handler=None, rectSize=None):
        if rectSize == None:
            image = pygame.image.load("assets/button.png").convert_alpha()
            size = (image.get_rect().width, image.get_rect().height)
        else:
            size = rectSize
            image = pygame.Surface(rectSize).convert_alpha()
            image.fill(colour)

        self.colour = colour
        self.image = image
        font = Font("assets/swiss911.ttf", 19)
        textImage = font.render(text, False, colours.BLACK)
        image.blit(textImage, 
                (image.get_rect().width - textImage.get_rect().width - 20,
                    image.get_rect().height - textImage.get_rect().height - 7))
    
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.applyColour(colour)
        self.highlighted = False
        self.beep = Sound("assets/audio/panel/202.wav")

    def handleEvent(self, event, clock):
        if (event.type == MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos) and self.visible == True):
            self.applyColour(colours.WHITE)
            self.highlighted = True
            self.beep.play()

        if (event.type == MOUSEBUTTONUP and self.highlighted and self.visible == True):
            self.applyColour(self.colour)
           
        return LcarsWidget.handleEvent(self, event, clock)
        
        
class LcarsNav(LcarsButton):
    """D pad buttons"""
    def __init__(self, colour, pos, text, handler=None):
        size = (70, 70)
        LcarsButton.__init__(self, colour, pos, text, handler, size)
        
class LcarsEMF(LcarsButton):
   def __init__(self, colour, pos, text, handler=None):
        size = (166, 54)
        self.emf_scanning = False
        LcarsButton.__init__(self, colour, pos, text, handler, size)
        
   def update(self, screen):
        if not self.visible:
            return
        #if self.scanning:
            #self.spectrum_image = pygame.image.load("/home/tricorder/rpi_lcars-master/spectrum.png")
            #print("loading image")

            
        screen.blit(self.image, self.rect)
         
        

		
class LcarsMicro(LcarsButton):
    def __init__(self, colour, pos, text, handler=None, rectSize=None):
        if rectSize == None:
            image = pygame.image.load("assets/button.png").convert_alpha()
            size = (image.get_rect().width, image.get_rect().height)
        else:
            size = rectSize
            image = pygame.Surface(rectSize).convert_alpha()
            image.fill(colour)

        self.colour = colour
        self.image = image
        font = Font("assets/swiss911.ttf", 19)
        textImage = font.render(text, False, colours.BLACK)
        image.blit(textImage, 
                (image.get_rect().width - textImage.get_rect().width - 20,
                    image.get_rect().height - textImage.get_rect().height - 7))
        self.cam = pygame.camera.Camera("/dev/video2",(1920,1080),"RGB")
        self.scan_start = False
        #os.system("v4l2-ctl --device /dev/video0 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG")
        #self.cam.start()
        #os.system("v4l2-ctl --device /dev/video0 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG")
        #print(self.cam.get_controls())
        #print(self.cam.get_size())
        #self.cam.set_size((1920,1080))
        #print(self.cam.get_size())
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.applyColour(colour)
        self.highlighted = False
        self.beep = Sound("assets/audio/panel/202.wav")

    #def handleEvent(self, event, clock):
    #    image = self.cam.get_image()
    #    self.sensor_gadget.image = image
    #    return LcarsWidget.handleEvent(self, event, clock)
    
    def update(self, screen):
        if not self.visible:
            return
        
        if self.line != None:
            self.line.next()
            if self.rect.center == self.line.pos:
                self.dirty = 0
                
            self.rect.center = self.line.pos
        else:
            self.dirty = 0

        if self.scanning:
            image = self.cam.get_image()
            #sc = pygame.transform.scale2x(image)
            #sc2 = pygame.transform.scale2x(sc)
            #p2 = pygame.Surface((640,480))
            #p2.blit(sc2,(-600*2-300,-90*2-250))
            self.micro_image = image #p2
            #screen.blit(image, self.rect)
        
        screen.blit(self.image, self.rect)
        
class LcarsSpectro(LcarsButton):
    def __init__(self, colour, pos, text, handler=None, rectSize=None):
        if rectSize == None:
            image = pygame.image.load("assets/button.png").convert_alpha()
            size = (image.get_rect().width, image.get_rect().height)
        else:
            size = rectSize
            image = pygame.Surface(rectSize).convert_alpha()
            image.fill(colour)

        self.colour = colour
        self.image = image
        self.cached_image = image
        self.analyze_complete = False
        font = Font("assets/swiss911.ttf", 19)
        textImage = font.render(text, False, colours.BLACK)
        image.blit(textImage, 
                (image.get_rect().width - textImage.get_rect().width - 20,
                    image.get_rect().height - textImage.get_rect().height - 7))
        self.cam = pygame.camera.Camera("/dev/video0",(1920,1080),"RGB")
        self.scan_start = False
        #os.system("v4l2-ctl --device /dev/video0 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG")
        #self.cam.start()
        #os.system("v4l2-ctl --device /dev/video0 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG")
        #print(self.cam.get_controls())
        #print(self.cam.get_size())
        #self.cam.set_size((1920,1080))
        #print(self.cam.get_size())
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.applyColour(colour)
        self.highlighted = False
        self.beep = Sound("assets/audio/panel/202.wav")

    #def handleEvent(self, event, clock):
    #    image = self.cam.get_image()
    #    self.sensor_gadget.image = image
    #    return LcarsWidget.handleEvent(self, event, clock)
    
    
    def update(self, screen):
        if not self.visible:
            return
        
        if self.line != None:
            self.line.next()
            if self.rect.center == self.line.pos:
                self.dirty = 0
                
            self.rect.center = self.line.pos
        else:
            self.dirty = 0
        

        if self.scanning:
            image = self.cam.get_image()
            sc = pygame.transform.scale2x(image)
            sc2 = pygame.transform.scale2x(sc)
            p2 = pygame.Surface((640,480))
            p2.blit(sc2,(-600*2-300,-90*2-250))
            self.micro_image = p2 # image
            self.cached_image = p2
            #screen.blit(image, self.rect)
        elif self.analyzing and not self.analyze_complete:
            self.cam.stop()
            threshold = 75  # Adjust as needed
            image_array = pygame.surfarray.array3d(self.cached_image) 
            non_black_pixels = np.where(np.any(image_array > threshold, axis=2))
            min_row, min_col = np.min(non_black_pixels, axis=1) 
            max_row, max_col = np.max(non_black_pixels, axis=1)
            spectrum_region = image_array[min_row:max_row+1, min_col:max_col+1]
            spectrum_surface = pygame.surfarray.make_surface(spectrum_region)
            #self.micro_image = add_white_border(spectrum_surface)
            self.micro_image = combine_images_stretch(spectrum_surface, to_grayscale(spectrum_surface), create_graph(spectrum_surface))
            self.analyze_complete = True
            
            #self.image = add_white_border(spectrum_surface) 

        
        screen.blit(self.image, self.rect)
        
def add_white_border(surface, border_width=5):
        """Adds a white border to a Pygame Surface."""
        rect = surface.get_rect()
        new_surface = pygame.Surface((rect.width + 2 * border_width, rect.height + 2 * border_width))
        new_surface.fill((255, 255, 255))  # Fill with white
        new_surface.blit(surface, (border_width, border_width))
        return new_surface     
        
def calculate_intensity_from_value(spectrum_image, width=500, height=300, axis=0, line_width=4):
    """Calculates intensity using the value dimension of HSV, averaged along the specified axis."""
    # Reshape for colorsys.rgb_to_hsv
    spectrum_array = pygame.surfarray.array3d(spectrum_image)
    reshaped_array = spectrum_array.reshape((-1, 3))
    # Convert RGB to HSV
    hsv_pixels = np.array([colorsys.rgb_to_hsv(*pixel / 255.0) for pixel in reshaped_array])
    # Reshape back to original dimensions with HSV values
    hsv_array = hsv_pixels.reshape(spectrum_array.shape)
    # Extract value (brightness) and calculate average along the specified axis
    column_intensities = hsv_array[:, :, 2].mean(axis=1)
    # Create a new Pygame Surface for the plot
    plot_surface = pygame.Surface((width, height))
    plot_surface.fill((0, 0, 0))  # Fill with black background

    # Scale and plot the column intensities as a line drawing
    scaled_intensities = column_intensities / np.max(column_intensities) * height
    points = [(int(i * width / len(column_intensities)), int(height - intensity))
              for i, intensity in enumerate(scaled_intensities)]
    pygame.draw.lines(plot_surface, (255, 255, 255), False, points, line_width)

    return plot_surface
    
def to_grayscale(surface):
  arr = pygame.surfarray.pixels3d(surface)
  # Average method for overall brightness
  avgs = [[(r + g + b) / 3 for r, g, b in row] for row in arr]  
  arr = np.array([[[avg, avg, avg] for avg in row] for row in avgs])
  grayscale_surface = pygame.surfarray.make_surface(arr)
  
  # Create a yellow surface with the same dimensions
  yellow_surface = pygame.Surface(grayscale_surface.get_size()).convert_alpha()
  yellow_surface.fill((255, 255, 0, 128))  # Yellow with alpha for transparency

  # Blend the yellow surface onto the grayscale surface
  grayscale_surface.blit(yellow_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

  return grayscale_surface
  
  
  
def create_graph(spectrum_image, width=500, height=300):
    # Convert the spectrum image to a NumPy array
    spectrum_array = pygame.surfarray.array3d(spectrum_image)
    window_size = 10 # for smoothing
    
    # Calculate average intensity for each column
    column_intensities =  np.max(spectrum_array, axis=2).mean(axis=1)  
    column_intensities_smooth = np.convolve(column_intensities, np.ones(window_size), 'valid') / window_size  
    column_intensities = column_intensities_smooth

    # Create a new Pygame Surface for the plot
    plot_surface = pygame.Surface((width, height))
    plot_surface.fill((0, 0, 0))  # Fill with black background
 
    # Scale and plot the column intensities as a line drawing
    scaled_intensities = column_intensities / np.max(column_intensities) * height
    points = [(int(i * width / len(column_intensities)), int(height - intensity))
              for i, intensity in enumerate(scaled_intensities)]
    pygame.draw.lines(plot_surface, (255, 222, 33), False, points, 4)  # Connect points with lines

    return plot_surface
    
def combine_images(image1, image2, image3, width=640, height=480):
    """Combines three images vertically, scaled to fit the specified width and height."""
    # Calculate scaling factors
    scale_factor = min(width / image1.get_width(), height / (image1.get_height() + image2.get_height() + image3.get_height()))

    # Scale images
    image1_scaled = pygame.transform.scale(image1, (int(image1.get_width() * scale_factor), int(image1.get_height() * scale_factor)))
    image2_scaled = pygame.transform.scale(image2, (int(image2.get_width() * scale_factor), int(image2.get_height() * scale_factor)))
    image3_scaled = pygame.transform.scale(image3, (int(image3.get_width() * scale_factor), int(image3.get_height() * scale_factor)))

    # Create combined surface
    total_height = image1_scaled.get_height() + image2_scaled.get_height() + image3_scaled.get_height()
    combined_surface = pygame.Surface((width, height))  # Use specified width and height

    # Blit images
    combined_surface.blit(image1_scaled, (0, 0))
    combined_surface.blit(image2_scaled, (0, image1_scaled.get_height()))
    combined_surface.blit(image3_scaled, (0, image1_scaled.get_height() + image2_scaled.get_height()))

    return combined_surface

def combine_images_stretch(image1, image2, image3, width=640, height=480):
    """Combines three images vertically, stretched to fit the specified width and height."""
    # Scale images (stretching to fit)
    image1_scaled = pygame.transform.scale(image1, (width, int(height / 3)))  # Stretch to 1/3 of height
    image2_scaled = pygame.transform.scale(image2, (width, int(height / 3)))  # Stretch to 1/3 of height
    image3_scaled = pygame.transform.scale(image3, (width, int(height / 3)))  # Stretch to 1/3 of height

    # Create combined surface
    combined_surface = pygame.Surface((width, height))  # Use specified width and height

    # Blit images
    combined_surface.blit(image1_scaled, (0, 0))
    combined_surface.blit(image2_scaled, (0, int(height / 3)))
    combined_surface.blit(image3_scaled, (0, int(2 * height / 3)))

    return combined_surface
	
class LcarsText(LcarsWidget):
    """Text that can be placed anywhere"""

    def __init__(self, colour, pos, message, size=1.0, background=None, handler=None):
        self.colour = colour
        self.background = background
        self.font = Font("assets/swiss911.ttf", int(19.0 * size))
        
        self.renderText(message)
        # center the text if needed 
        if (pos[1] < 0):
            pos = (pos[0], 400 - self.image.get_rect().width / 2)
            
        LcarsWidget.__init__(self, colour, pos, None, handler)

    def renderText(self, message):        
        if (self.background == None):
            self.image = self.font.render(message, True, self.colour)
        else:
            self.image = self.font.render(message, True, self.colour, self.background)
        
    def setText(self, newText):
        self.renderText(newText)

class LcarsBlockLarge(LcarsButton):
    """Left navigation block - large version"""

    def __init__(self, colour, pos, text, handler=None):
        size = (181, 253)
        LcarsButton.__init__(self, colour, pos, text, handler, size)

class LcarsBlockMedium(LcarsButton):
   """Left navigation block - medium version"""

   def __init__(self, colour, pos, text, handler=None):
        size = (181, 166)
        LcarsButton.__init__(self, colour, pos, text, handler, size)

class LcarsBlockSmall(LcarsButton):
   """Left navigation block - small version"""

   def __init__(self, colour, pos, text, handler=None):
        size = (181, 102)
        LcarsButton.__init__(self, colour, pos, text, handler, size)

class LcarsBlockTop(LcarsButton):
   """Left navigation block - small version"""

   def __init__(self, colour, pos, text, handler=None):
        size = (166, 54)
        LcarsButton.__init__(self, colour, pos, text, handler, size)

    
