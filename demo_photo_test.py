from vision.photo_analyzer import analyze_shoe_photo

known_brands = ["Nike", "Adidas", "Jordan", "New Balance", "Puma", "Reebok", "Asics"]
known_models = ["Air Jordan 1", "Air Jordan 11", "Yeezy 350", "Samba", "Ultraboost", "Superstar"]

result = analyze_shoe_photo("test_images/test_image1.png", known_brands, known_models)
if result is None:
    print("Could not identify shoe from photo.")
else:
    print(f"Brand: {result.brand}")
    print(f"Model: {result.model_name}")
    print(f"Size: {result.size} {result.size_unit}")
    print(f"Condition: {result.condition_score}")
    print(f"Confidence: {result.confidence}")
    print(f"Raw input log: {result.raw_input}")