from livefeed import livefeed

DROIDCAM_URL = "http://192.168.1.100:4747/video"


if __name__ == "__main__":
    livefeed(DROIDCAM_URL, mirror=False)
