#!/usr/bin/env python3
"""
microscope_widget.py - LCARS Microscope Widget

Handles microscope live view, image capture, and browsing with support for
multiple image categories/groups based on filename prefixes.
"""

import pygame
import glob
import os
from datetime import datetime
from ui.widgets.lcars_widgets import LcarsWidget
from ui import colours


class LcarsMicroscopeWidget(LcarsWidget):
    """
    Microscope widget with live view and intelligent image browsing
    
    Supports multiple image categories/groups based on filename prefixes:
    - microscope_* : General microscope images
    - specimen_* : Specimen samples
    - slide_* : Slide preparations
    - culture_* : Culture samples
    etc.
    """
    
    def __init__(self, pos, size, camera, screenshot_dir, micro_button):
        """
        Initialize microscope widget
        
        Args:
            pos: (x, y) position tuple
            size: (width, height) size tuple
            camera: Camera object for live view
            screenshot_dir: Directory to save/load images
            micro_button: LcarsMicro button object (for scanning flag sync)
        """
        self.size = size
        self.image = pygame.Surface(size)
        self.rect = self.image.get_rect()
        self.rect.topleft = pos
        
        LcarsWidget.__init__(self, colours.BLACK, pos, None)
        
        # Camera and directory
        self.camera = camera
        self.screenshot_dir = screenshot_dir
        self.micro_button = micro_button  # Keep reference to sync scanning flag
        
        # View state
        self.scanning = False  # Live view mode
        self.reviewing = False  # Image review mode
        
        # Current image being reviewed
        self.current_image_index = 0
        
    
        # Image groups/categories
        self.image_groups = {
            'microscope': {
                'prefix': 'microscope_',
                'name': 'General',
                'description': 'General unsorted microscope images'
            },
            'amber': {
                'prefix': 'amber_',
                'name': 'Amber',
                'description': 'Fossils in amber'
            },
            'fiber': {
                'prefix': 'fiber_',
                'name': 'Fiber',
                'description': 'Textiles and fibers'
            },
            'rocks': {
                'prefix': 'rocks_',
                'name': 'Rocks',
                'description': 'Mineral samples'
            },
            'spectro': {
                'prefix': 'spectro_',
                'name': 'Spectro',
                'description': 'Spectroscope spectra'
            }
        }
        
        # Current group filter (None = all images)
        self.current_group = None
        
        # Current save prefix (which group to save to)
        self.save_prefix = 'microscope_'
        
        # Cached file list
        self._cached_files = []
        self._cache_timestamp = 0
        
    def start_live_view(self):
        """Start live camera view"""
        if not self.scanning:
            self.camera.start()
        self.scanning = True
        self.reviewing = False
        
        # Sync with micro button
        self.micro_button.scanning = True
        
        print("Microscope: Live view started")
    
    def stop_live_view(self):
        """Stop live camera view"""
        if self.scanning:
            self.camera.stop()
        self.scanning = False
        
        # Sync with micro button
        self.micro_button.scanning = False
        
        print("Microscope: Live view stopped")
    
    def capture_image(self, screen_surface):
        """
        Capture current view to file
        
        Args:
            screen_surface: Pygame surface to capture (full screen for cropping later)
            
        Returns:
            Filename of saved image
        """
        timestamp = datetime.now().strftime("%y.%m.%d.%H.%M.%S")
        filename = "{}{}.jpg".format(self.save_prefix, timestamp)
        filepath = os.path.join(self.screenshot_dir, filename)
        
        print("Attempting to save: {}".format(filepath))
        print("  Directory: {}".format(self.screenshot_dir))
        print("  Filename: {}".format(filename))
        
        # Make sure directory exists
        if not os.path.exists(self.screenshot_dir):
            try:
                os.makedirs(self.screenshot_dir)
                print("  Created directory: {}".format(self.screenshot_dir))
            except Exception as e:
                print("  Error creating directory {}: {}".format(self.screenshot_dir, e))
                return None
        else:
            print("  Directory exists: {}".format(self.screenshot_dir))
        
        # Check if directory is writable
        if not os.access(self.screenshot_dir, os.W_OK):
            print("  ERROR: Directory is not writable!")
            return None
        else:
            print("  Directory is writable")
        
        try:
            # Save the full screen surface
            # This will be cropped when loading for review
            print("  Calling pygame.image.save()...")
            pygame.image.save(screen_surface, filepath)
            print("  SUCCESS: Saved screenshot: {} (group: {})".format(filename, self._get_group_name_from_prefix(self.save_prefix)))
            
            # Verify file was created
            if os.path.exists(filepath):
                print("  File verified: {} bytes".format(os.path.getsize(filepath)))
            else:
                print("  WARNING: File was not created!")
            
            # Invalidate cache
            self._cache_timestamp = 0
            
            return filename
        except Exception as e:
            print("  Error saving image to {}: {}".format(filepath, e))
            import traceback
            traceback.print_exc()
            return None
    
    def _get_group_name_from_prefix(self, prefix):
        """Get human-readable group name from prefix"""
        for group_id, group_info in self.image_groups.items():
            if group_info['prefix'] == prefix:
                return group_info['name']
        return "Unknown"
    
    def get_image_files(self, group_filter=None, force_refresh=False):
        """
        Get list of image files, optionally filtered by group
        
        Args:
            group_filter: Group ID to filter by (None = all images)
            force_refresh: Force refresh of cached file list
            
        Returns:
            List of file paths sorted by modification time (newest first)
        """
        # Check if cache is still valid (within 1 second)
        current_time = pygame.time.get_ticks()
        cache_valid = (current_time - self._cache_timestamp) < 1000 and not force_refresh
        
        if cache_valid and group_filter == self.current_group:
            return self._cached_files
        
        # Build file pattern
        if group_filter and group_filter in self.image_groups:
            pattern = self.image_groups[group_filter]['prefix'] + "*.jpg"
        else:
            # Get all images from all groups
            pattern = "*.jpg"
        
        # Get matching files
        search_pattern = os.path.join(self.screenshot_dir, pattern)
        files = glob.glob(search_pattern)
        
        # Filter to only include files from known groups if no specific filter
        if group_filter is None:
            known_prefixes = [info['prefix'] for info in self.image_groups.values()]
            files = [f for f in files if any(os.path.basename(f).startswith(p) for p in known_prefixes)]
        
        # Sort by modification time (newest first)
        sorted_files = sorted(files, key=lambda f: os.path.getmtime(f), reverse=True)
        
        # Update cache
        self._cached_files = sorted_files
        self._cache_timestamp = current_time
        self.current_group = group_filter
        
        return sorted_files
    
    def get_group_counts(self):
        """
        Get count of images in each group
        
        Returns:
            Dictionary mapping group_id to count
        """
        counts = {}
        for group_id, group_info in self.image_groups.items():
            pattern = os.path.join(self.screenshot_dir, group_info['prefix'] + "*.jpg")
            files = glob.glob(pattern)
            counts[group_id] = len(files)
        return counts
    
    def enter_review_mode(self):
        """
        Enter review mode to browse captured images
        
        """
        self.stop_live_view()
        self.reviewing = True
        self.current_image_index = 0
        
        files = self.get_image_files(self.current_group, force_refresh=True)
        if files:
            print("Microscope: Review mode - {} images{}".format(
                len(files),
                " ({})".format(self.image_groups[self.current_group]['name']) if self.current_group else ""
            ))
        else:
            print("Microscope: No images to review")
    
    def cycle_group_filter(self, direction):
        """
        Cycle through group filters while in review mode
        
        Args:
            direction: -1 for previous, 1 for next
        """
        if not self.reviewing:
            return
        
        # List of groups: None (all), then each group ID
        groups = [None] + list(self.image_groups.keys())
        
        # Find current position
        try:
            current_idx = groups.index(self.current_group)
        except ValueError:
            current_idx = 0
        
        # Move to next/previous
        new_idx = (current_idx + direction) % len(groups)
        new_group = groups[new_idx]
        
        # Update filter and reset to first image
        self.current_group = new_group
        self.current_image_index = 0
        
        # Update save prefix to match selected group
        self.set_save_to_current_group()
        
        # Force refresh file list
        files = self.get_image_files(new_group, force_refresh=True)
        
        if new_group:
            print("Filter: {} ({} images)".format(
                self.image_groups[new_group]['name'],
                len(files)
            ))
        else:
            print("Filter: ALL ({} images)".format(len(files)))
    
    def navigate_images(self, delta):
        """
        Navigate through images in review mode
        
        Args:
            delta: Number of images to move (negative = backward, positive = forward)
        """
        if not self.reviewing:
            return
        
        files = self.get_image_files(self.current_group)
        if not files:
            return
        
        self.current_image_index += delta
        
        # Wrap around
        if self.current_image_index >= len(files):
            self.current_image_index = 0
        elif self.current_image_index < 0:
            self.current_image_index = len(files) - 1
        
        print("Image {}/{}: {}".format(
            self.current_image_index + 1,
            len(files),
            os.path.basename(files[self.current_image_index])
        ))
    
    def jump_to_image(self, index):
        """Jump to specific image index"""
        if not self.reviewing:
            return
        
        files = self.get_image_files(self.current_group)
        if 0 <= index < len(files):
            self.current_image_index = index
    
    def set_save_group(self, group_id):
        """
        Set which group new images will be saved to
        
        Args:
            group_id: Group ID from image_groups
        """
        if group_id in self.image_groups:
            self.save_prefix = self.image_groups[group_id]['prefix']
            print("Saving to group: {}".format(self.image_groups[group_id]['name']))
        else:
            print("Unknown group: {}".format(group_id))
    
    def cycle_save_group(self, direction=1):
        """
        Cycle to next/previous save group
        
        Args:
            direction: 1 for next, -1 for previous
        """
        group_ids = list(self.image_groups.keys())
        
        # Find current group
        current_idx = 0
        for i, group_id in enumerate(group_ids):
            if self.image_groups[group_id]['prefix'] == self.save_prefix:
                current_idx = i
                break
        
        # Move to next/previous group
        new_idx = (current_idx + direction) % len(group_ids)
        self.set_save_group(group_ids[new_idx])
    
    def set_save_to_current_group(self):
        """Set save prefix to match the currently selected review group"""
        if self.current_group:
            self.save_prefix = self.image_groups[self.current_group]['prefix']
            print("Save prefix set to: {}".format(self.image_groups[self.current_group]['name']))
        else:
            # Default to first group if viewing ALL
            first_group = list(self.image_groups.keys())[0]
            self.save_prefix = self.image_groups[first_group]['prefix']
            print("Save prefix set to: {}".format(self.image_groups[first_group]['name']))
    
    def get_current_image(self):
        """
        Get the current image surface for display
        
        Returns:
            Pygame surface of current image, or None
        """
        if self.scanning:
            # Live view - return camera image from micro button
            # The LcarsMicro button sets micro_image when scanning
            return self.micro_button.micro_image if hasattr(self.micro_button, 'micro_image') else None
        
        elif self.reviewing:
            # Review mode - load and return current image
            files = self.get_image_files(self.current_group)
            if files and 0 <= self.current_image_index < len(files):
                try:
                    img = pygame.image.load(files[self.current_image_index])
                    return img
                except Exception as e:
                    print("Error loading image: {}".format(e))
                    return None
        
        return None
    
    def get_status_text(self):
        """
        Get status text for display
        
        Returns:
            List of strings for text display
        """
        lines = []
        
        if self.scanning:
            lines.append("LIVE VIEW")
            lines.append("")
            lines.append("Save to: {}".format(self._get_group_name_from_prefix(self.save_prefix)))
            lines.append("")
            lines.append("Press RECORD to capture")
            
        elif self.reviewing:
            files = self.get_image_files(self.current_group)
            if files:
                lines.append("REVIEW MODE")
                if self.current_group:
                    lines.append("Group: {}".format(self.image_groups[self.current_group]['name']))
                else:
                    lines.append("All Images")
                lines.append("")
                lines.append("Image {}/{}".format(self.current_image_index + 1, len(files)))
                lines.append("")
                lines.append(os.path.basename(files[self.current_image_index]))
            else:
                lines.append("NO IMAGES")
        else:
            lines.append("MICROSCOPE")
            
        return lines
    
    def select_group_by_name(self, group_name):
        """
        Select a group by its display name (for click handling)
        
        Args:
            group_name: Display name of the group (e.g., "General", "Specimens", "ALL")
        """
        if self.reviewing:
            # Review mode: change filter
            # Handle "ALL" selection
            if "ALL" in group_name:
                self.current_group = None
                self.current_image_index = 0
                self.set_save_to_current_group()
                files = self.get_image_files(None, force_refresh=True)
                print("Filter: ALL ({} images)".format(len(files)))
                return True
            
            # Find matching group
            for group_id, group_info in self.image_groups.items():
                if group_info['name'] in group_name:
                    self.current_group = group_id
                    self.current_image_index = 0
                    self.set_save_to_current_group()
                    files = self.get_image_files(group_id, force_refresh=True)
                    print("Filter: {} ({} images)".format(group_info['name'], len(files)))
                    return True
        else:
            # Live mode: change save group
            # Handle "ALL" selection (default to first group)
            if "ALL" in group_name:
                first_group = list(self.image_groups.keys())[0]
                self.set_save_group(first_group)
                return True
            
            # Find matching group
            for group_id, group_info in self.image_groups.items():
                if group_info['name'] in group_name:
                    self.set_save_group(group_id)
                    return True
        
        return False
    
    def get_group_browser_text(self):
        """
        Get text for group browser display
        
        Returns:
            List of strings showing available groups and counts
        """
        lines = [""]
        
        counts = self.get_group_counts()
        total = sum(counts.values())
        
        # Determine which group is "selected" (for >>> marker)
        # In review mode: show current filter
        # In live mode: show current save group
        selected_group = None
        if self.reviewing:
            selected_group = self.current_group
        else:
            # Find which group matches the save prefix
            for group_id, group_info in self.image_groups.items():
                if group_info['prefix'] == self.save_prefix:
                    selected_group = group_id
                    break
        
        # All images option
        if selected_group is None:
            lines.append(">>> ALL ({})".format(total))
        else:
            lines.append("ALL ({})".format(total))
        
        # Individual groups
        for group_id, group_info in self.image_groups.items():
            count = counts.get(group_id, 0)
            
            if selected_group == group_id:
                lines.append(">>> {} ({})".format(group_info['name'], count))
            else:
                lines.append("{} ({})".format(group_info['name'], count))
        
        return lines
    
    def update(self, screen):
        """Update widget rendering"""
        if not self.visible:
            return
        
        # Clear to black
        self.image.fill((0, 0, 0))
        
        # Get current image
        img = self.get_current_image()
        
        if img:
            # Crop the image to show only the 640x480 microscope view
            # The screenshot is of the full screen, but we only want the gadget area
            # Original code: p2.blit(sc2,(-600*2-300,-90*2-250))
            # This crops out the center microscope viewing area from the full image
            
            if self.reviewing:
                # Reviewing saved screenshot - crop to show only microscope area
                # Screenshots are full screen captures, need to extract the 640x480 view
                cropped = pygame.Surface((640, 480))
                # Crop offset matches the gadget position (187, 299)
                cropped.blit(img, (-299,-187))
                self.image.blit(cropped, (0, 0))
            else:
                # Live view from camera - display directly
                # Camera returns full resolution, crop as needed
                self.image.blit(img, (0, 0))
        
        # Blit to screen
        screen.blit(self.image, self.rect)
        
        self.dirty = 0
