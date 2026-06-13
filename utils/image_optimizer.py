"""
Image Optimizer Module
Compresses and optimizes images before WordPress upload.
"""
import os
from PIL import Image
import io


def optimize_image(image_path: str, max_width: int = 1200, quality: int = 85) -> str:
    """
    Optimizes an image for web:
    - Converts to WebP format (better compression)
    - Resizes if larger than max_width
    - Compresses to target quality
    
    Returns path to optimized image (WebP format).
    """
    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        return image_path
    
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize if too large
            original_width, original_height = img.size
            if original_width > max_width:
                ratio = max_width / original_width
                new_height = int(original_height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                print(f"📐 Resized image from {original_width}x{original_height} to {max_width}x{new_height}")
            
            # Generate output path (WebP format)
            base_name = os.path.splitext(image_path)[0]
            webp_path = f"{base_name}_optimized.webp"
            
            # Save as WebP with compression
            img.save(webp_path, 'WebP', quality=quality, optimize=True)
            
            # Compare file sizes
            original_size = os.path.getsize(image_path)
            optimized_size = os.path.getsize(webp_path)
            savings = ((original_size - optimized_size) / original_size) * 100
            
            print(f"✅ Image optimized: {original_size/1024:.1f}KB → {optimized_size/1024:.1f}KB ({savings:.1f}% smaller)")
            
            return webp_path
            
    except Exception as e:
        print(f"⚠️ Image optimization failed: {e}")
        return image_path


def get_image_dimensions(image_path: str) -> tuple:
    """Returns (width, height) of an image."""
    try:
        with Image.open(image_path) as img:
            return img.size
    except:
        return (0, 0)


def generate_responsive_sizes(image_path: str, sizes: list = [400, 800, 1200]) -> list:
    """
    Generates multiple sizes of an image for responsive loading.
    Returns list of (width, path) tuples.
    """
    results = []
    
    if not os.path.exists(image_path):
        return results
    
    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            original_width, original_height = img.size
            base_name = os.path.splitext(image_path)[0]
            
            for target_width in sizes:
                if target_width >= original_width:
                    continue
                    
                ratio = target_width / original_width
                new_height = int(original_height * ratio)
                resized = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
                
                output_path = f"{base_name}_{target_width}w.webp"
                resized.save(output_path, 'WebP', quality=80, optimize=True)
                results.append((target_width, output_path))
                
            print(f"✅ Generated {len(results)} responsive image sizes")
            
    except Exception as e:
        print(f"⚠️ Responsive image generation failed: {e}")
    
    return results
