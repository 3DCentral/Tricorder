import pygame
import tifffile
import numpy as np
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
FILE_PATH = "usgs/USGS_13_n38w078_20211220.tif"
SCREEN_SIZE = (800, 600)
CONTOUR_LEVELS = 15
PAN_SPEED = 15
OUTLIER_THRESHOLD = 3.0  # Number of standard deviations above mean to consider spurious
SAMPLE_SIZE = 500  # Only sample this many segments for statistics (much faster!)

def calculate_segment_length(p1, p2):
    """Calculate Euclidean distance between two points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return np.sqrt(dx*dx + dy*dy)

def analyze_contour_segments_fast(all_paths, outlier_threshold, sample_size=SAMPLE_SIZE):
    """Fast sampling-based analysis of contour segments."""
    all_lengths = []
    
    # Collect all segment lengths (but we'll sample from them)
    for path in all_paths:
        points = path.vertices
        if len(points) > 1:
            for i in range(1, len(points)):
                length = calculate_segment_length(points[i-1], points[i])
                all_lengths.append(length)
                
                # Early exit if we have enough samples
                if len(all_lengths) >= sample_size:
                    break
        if len(all_lengths) >= sample_size:
            break
    
    if len(all_lengths) == 0:
        return 100  # Default threshold
    
    # Use numpy for fast statistics
    lengths_array = np.array(all_lengths)
    mean_length = np.mean(lengths_array)
    std_length = np.std(lengths_array)
    
    # Threshold is mean + N standard deviations
    threshold = mean_length + (outlier_threshold * std_length)
    
    return threshold

def filter_contour_path_fast(points, max_length):
    """Fast filtering using numpy operations where possible."""
    if len(points) < 2:
        return []
    
    # Convert to numpy array for vectorized operations
    points_array = np.array(points)
    
    # Calculate all segment lengths at once
    diffs = np.diff(points_array, axis=0)
    lengths = np.sqrt(diffs[:, 0]**2 + diffs[:, 1]**2)
    
    # Find where segments are too long (spurious connections)
    breaks = np.where(lengths > max_length)[0]
    
    if len(breaks) == 0:
        # No spurious connections, return the whole path
        return [points]
    
    # Split into segments at break points
    segments = []
    start_idx = 0
    
    for break_idx in breaks:
        # Add segment up to (but not including) the break
        if break_idx > start_idx:
            segment = points[start_idx:break_idx+1]
            if len(segment) > 1:
                segments.append(segment)
        # Start next segment after the break
        start_idx = break_idx + 1
    
    # Add final segment
    if start_idx < len(points):
        segment = points[start_idx:]
        if len(segment) > 1:
            segments.append(segment)
    
    return segments

def get_visible_contours(data, x, y, zoom, screen_size, outlier_threshold):
    """Calculates contours with fast adaptive filtering."""
    sw, sh = screen_size
    
    # Buffer zone
    buffer = int(max(sw, sh) / zoom * 0.3)
    
    x_start = max(0, int(-x) - buffer)
    y_start = max(0, int(-y) - buffer)
    x_end = min(data.shape[1], int(-x + sw / zoom) + buffer)
    y_end = min(data.shape[0], int(-y + sh / zoom) + buffer)

    visible_x_start = max(0, int(-x))
    visible_y_start = max(0, int(-y))

    patch = data[y_start:y_end, x_start:x_end]
    if patch.size == 0: 
        return None, 0, 0, {}

    # Generate contours
    fig, ax = plt.subplots()
    contours = ax.contour(patch, levels=CONTOUR_LEVELS)
    plt.close(fig)

    # Fast sampling-based threshold calculation
    all_paths = contours.get_paths()
    adaptive_threshold = analyze_contour_segments_fast(all_paths, outlier_threshold)

    # Create surface
    surf = pygame.Surface((x_end - x_start, y_end - y_start), pygame.SRCALPHA)
    surf.fill((255, 255, 255, 0))

    # Statistics
    total_segments = 0
    filtered_segments = 0
    
    # Draw contours with filtering
    for path in all_paths:
        points = path.vertices
        if len(points) > 1:
            total_segments += 1
            # Fast filtering
            segments = filter_contour_path_fast(points, adaptive_threshold)
            
            if len(segments) == 0:
                filtered_segments += 1
            
            # Draw each valid segment
            for segment in segments:
                if len(segment) > 1:
                    # Convert numpy array back to list for pygame
                    segment_list = segment.tolist() if isinstance(segment, np.ndarray) else segment
                    pygame.draw.lines(surf, (80, 50, 20), False, segment_list, 1)
    
    offset_x = x_start - visible_x_start
    offset_y = y_start - visible_y_start
    
    stats = {
        'threshold': adaptive_threshold,
        'total_paths': total_segments,
        'filtered': filtered_segments
    }
    
    return surf, offset_x, offset_y, stats

def main():
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Fast Adaptive Topo Map - WASD to pan, Arrows to zoom, +/- sensitivity")
    
    # Use memory mapping
    with tifffile.TiffFile(FILE_PATH) as tif:
        raw_data = tif.asarray(out='memmap')
    
    print(f"Loaded {raw_data.shape[1]}x{raw_data.shape[0]} elevation data")

    cam_x, cam_y = 0, 0
    zoom = 1.0
    outlier_threshold = OUTLIER_THRESHOLD
    clock = pygame.time.Clock()
    stats = {}
    fps = 0
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: 
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS:
                    outlier_threshold += 0.25
                    print(f"Outlier threshold: {outlier_threshold:.2f} std devs")
                elif event.key == pygame.K_MINUS:
                    outlier_threshold = max(1.0, outlier_threshold - 0.25)
                    print(f"Outlier threshold: {outlier_threshold:.2f} std devs")

        keys = pygame.key.get_pressed()
        if keys[pygame.K_w]: cam_y += PAN_SPEED / zoom
        if keys[pygame.K_s]: cam_y -= PAN_SPEED / zoom
        if keys[pygame.K_a]: cam_x += PAN_SPEED / zoom
        if keys[pygame.K_d]: cam_x -= PAN_SPEED / zoom
        if keys[pygame.K_UP]: zoom *= 1.05
        if keys[pygame.K_DOWN]: zoom = max(0.1, zoom * 0.95)

        screen.fill((240, 240, 230))

        # Generate filtered contours
        result = get_visible_contours(raw_data, cam_x, cam_y, zoom, SCREEN_SIZE, outlier_threshold)
        
        if result[0]:
            visible_surf, offset_x, offset_y, stats = result
            scaled = pygame.transform.smoothscale(visible_surf, 
                     (int(visible_surf.get_width() * zoom), int(visible_surf.get_height() * zoom)))
            screen.blit(scaled, (int(offset_x * zoom), int(offset_y * zoom)))

        # Display info overlay
        fps = clock.get_fps()
        font = pygame.font.Font(None, 24)
        info_lines = [
            f"FPS: {fps:.1f} | Zoom: {zoom:.2f}x",
            f"Threshold: {stats.get('threshold', 0):.1f}px (±{outlier_threshold:.2f}σ)",
            f"Paths: {stats.get('total_paths', 0)} | Filtered: {stats.get('filtered', 0)}",
            f"+/- to adjust sensitivity"
        ]
        
        y_pos = 10
        for line in info_lines:
            text = font.render(line, True, (50, 50, 50))
            bg_rect = text.get_rect(topleft=(10, y_pos))
            bg_rect.inflate_ip(10, 4)
            pygame.draw.rect(screen, (240, 240, 230, 200), bg_rect)
            screen.blit(text, (10, y_pos))
            y_pos += 25

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
