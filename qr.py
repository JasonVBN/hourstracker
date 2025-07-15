import qrcode

def make_qr(data:str):
    img = qrcode.make(data)
    return img

if __name__ == "__main__":
    make_qr("https://example.com")
    print("QR code generated and saved as 'qr.png'")