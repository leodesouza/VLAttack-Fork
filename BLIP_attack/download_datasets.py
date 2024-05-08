import io

import requests
import zipfile
import os


def download(url, extract_dir):
    response = requests.get(train_url)
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            zip_file.extractall(extract_dir)
        print(f"File {url} downloaded")
    else:
        print(f"Failed to donwload File {url}")


if __name__ == '__main__':
    train_url = 'http://images.cocodataset.org/zips/train2014.zip'
    train_path = ''
    download(train_url, train_path)

    val_url = 'http://images.cocodataset.org/zips/val2014.zip'
    val_path = ''
    download(val_url, val_path)
