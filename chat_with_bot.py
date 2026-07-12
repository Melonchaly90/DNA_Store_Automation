from webhook.main import process_customer_message
from models.webhook_payload import WhatsAppMessage, TextContent, ImageContent
import time

print("=== Chat with DNA Thrift Bot ===")
print("Type your message, or type 'photo' to send a test image, or 'quit' to exit.\n")

phone = "923001234567"  # pretend this is you

while True:
    user_input = input("You: ").strip()

    if user_input.lower() == "quit":
        break

    if user_input.lower() == "photo":
        image_path = input("Enter image path (e.g. test_images/test_image1.png): ").strip()
        message = WhatsAppMessage(
            **{"from": phone},
            id=f"msg_{int(time.time())}",
            timestamp=str(int(time.time())),
            type="image",
            image=ImageContent(id=image_path)  # using local path directly for this test script
        )
    else:
        message = WhatsAppMessage(
            **{"from": phone},
            id=f"msg_{int(time.time())}",
            timestamp=str(int(time.time())),
            type="text",
            text=TextContent(body=user_input)
        )

    reply = process_customer_message(message)
    print(f"Bot: {reply}\n")