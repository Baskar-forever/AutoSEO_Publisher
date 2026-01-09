# main.py
import os
from dotenv import load_dotenv
from article_generater import ArticleGenerator
from utils.link_audit import audit_and_fix_links
from utils.faq_injector import inject_faq_section
from wordpress_uploader import upload_image_to_wordpress,process_and_publish

load_dotenv()

if __name__ == "__main__":
    print("Starting full AI SEO → WordPress automation pipeline...")

    generator = ArticleGenerator()
    html_output, local_image_path = generator.generate_article()
    html_output = audit_and_fix_links(html_output)
    html_output = inject_faq_section(generator.my_llm,html_output)
    
    if not html_output:
        print("❌ Article generation failed. Exiting.")
        exit()
    
    print(f"Article generated. Local image path: {local_image_path}")
    
    new_image_url = None
    media_id = None
    if local_image_path: 
        # 2️ Upload the image to WordPress
        media_id, new_image_url = upload_image_to_wordpress(local_image_path)
    else:
        print("No local image path returned. Skipping image upload.")


    # 4️ Post the final article to WordPress
    if html_output:
        process_and_publish(html_content=html_output,local_image_path=local_image_path)
        
    else:
        print("❌ Could not extract title or body. Skipping post upload.")