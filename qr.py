import qrcode

url = "https://0869-61-254-34-231.ngrok-free.app"
img = qrcode.make(url)
img.save("flask_qr.png")