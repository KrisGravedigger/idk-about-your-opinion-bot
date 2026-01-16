"""
Script to create an IDK-themed icon for the executable.
Creates a simple, clean icon with "IDK" text.
"""
from PIL import Image, ImageDraw, ImageFont
import os

# Create a new image with a gradient background
size = 256
image = Image.new('RGB', (size, size), color='white')
draw = ImageDraw.Draw(image)

# Create a nice gradient background (dark blue to light blue)
for y in range(size):
    # Gradient from dark blue (#1a1f3a) to lighter blue (#2d4a7c)
    r = int(26 + (45 - 26) * (y / size))
    g = int(31 + (74 - 31) * (y / size))
    b = int(58 + (124 - 58) * (y / size))
    draw.rectangle([(0, y), (size, y+1)], fill=(r, g, b))

# Add circular background for text
circle_center = size // 2
circle_radius = int(size * 0.42)
draw.ellipse(
    [(circle_center - circle_radius, circle_center - circle_radius),
     (circle_center + circle_radius, circle_center + circle_radius)],
    fill='#1a1f3a',
    outline='#4a9eff',
    width=6
)

# Try to use a bold font, fall back to default if not available
try:
    # Try common system fonts
    font_size = int(size * 0.35)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ]
    font = None
    for font_path in font_paths:
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, font_size)
            break
    if font is None:
        font = ImageFont.load_default()
except Exception as e:
    print(f"Could not load custom font: {e}")
    font = ImageFont.load_default()

# Draw "IDK" text
text = "IDK"
# Get text bounding box for centering
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
text_x = (size - text_width) // 2
text_y = (size - text_height) // 2 - int(size * 0.03)  # Slight upward adjustment

# Draw text with a subtle shadow effect
shadow_offset = 3
draw.text((text_x + shadow_offset, text_y + shadow_offset), text, fill='#0a0f1a', font=font)
draw.text((text_x, text_y), text, fill='#4a9eff', font=font)

# Add a subtle glow effect
for offset in [1, 2]:
    draw.text((text_x - offset, text_y), text, fill='#2d6eb8', font=font)
    draw.text((text_x + offset, text_y), text, fill='#2d6eb8', font=font)
    draw.text((text_x, text_y - offset), text, fill='#2d6eb8', font=font)
    draw.text((text_x, text_y + offset), text, fill='#2d6eb8', font=font)

# Redraw the main text on top
draw.text((text_x, text_y), text, fill='#4a9eff', font=font)

# Save as ICO (multiple sizes for better compatibility)
icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
images = [image.resize(size, Image.Resampling.LANCZOS) for size in icon_sizes]

# Save as .ico
output_path = 'icon.ico'
images[0].save(output_path, format='ICO', sizes=icon_sizes, append_images=images[1:])
print(f"✅ Icon created successfully: {output_path}")

# Also save as PNG for preview
image.save('icon_preview.png', format='PNG')
print(f"✅ Preview image created: icon_preview.png")
