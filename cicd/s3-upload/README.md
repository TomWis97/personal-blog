# s3-upload
Uploads images to S3 bucket.

The script will search in a given directory (album title) for files to upload. If alt.txt exists, it will add the alt texts of those files as a base64 encoded value as `x-amz-meta-alttext` metadata to that file.

## Requirements
- Have Python dependencies installed as in `../requirements.txt`.
- Provide AWS credentials for upload through `../env` (template is available as `../env.dist`).

## Usage
1. Create a subdirectory in here. The name of the directory will be the album name.
2. Place images in said directory. Ordering of album will be through alphabetical sort.
3. Create a file called `alt.txt` with image alt texts. This file will need to be formatted as follows:
```
filename1.jpg|This is some alt text.
filename2.jpg|More alt text. 🎉
```
4. Run the script with the album name as parameter: `./upload.py myalbum`. It'll upload all files to S3 (except for `alt.txt`) to S3, adding alt texts for all listed files.
