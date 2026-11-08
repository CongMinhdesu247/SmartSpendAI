"""Point the desktop launcher to the same HTTPS app used on iPhone."""
import argparse
from backend.access import normalize_public_url
from backend.database import load_config, save_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='HTTPS URL supplied by hosting')
    args = parser.parse_args()
    value = args.url or input('Dan dia chi HTTPS cua app da trien khai: ').strip()
    try:
        url = normalize_public_url(value)
        if not url:
            raise ValueError('Dia chi khong duoc de trong')
        config = load_config()
        config['cloud_url'] = url
        save_config(config)
        print('Da ket noi desktop voi app cloud. Mo lai run_app.bat.')
    except ValueError:
        print('Dia chi chua hop le. Dung URL HTTPS, khong kem duong dan hay mat khau.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
