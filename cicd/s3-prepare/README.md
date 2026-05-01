# s3-prepare
Downloads images from S3 bucket and prepares images for build of container images.

The script will search in the supplied path for all `*.md` files. Within those files, the script will search for references to albums (see below). It will retrieve those images and resize them to a maximum of 1920 by 1080 px and place those images in the same directory as the Markdown files.   
In turn, the script will replace the album references with the actual Markdown code.

This script expects each album to have a directory in the root of the S3 bucket. Within those directories each picture is an object. Each object _may_ have an alt-text in the metadata as `x-amz-meta-alttext`, which is base64 encoded.

## Usage in Markdown: References to albums.
You can refer to albums in two ways: one for the album itself and one for links to the original files in the S3 bucket.

### References to album itself
The following line is a reference to an album:
```
!Album[myalbum]
```
This will retrieve the album "myalbum" from the S3 bucket. It'll look for the `myalbum` directory in the S3 bucket and retrieve all files, resize them, convert to JPEG (and renaming extension if relevant) and place them with the same file names as in the bucket in the same directory as the `.md` file.

Also, it will render the album with the files discovered in the bucket, including the alt texts. For example, it will replace `!Album[myalbum]` with:

```
![This is some alt text.](filename1.jpg)
![More alt text. 🎉](filename2.jpg)
```

### References to files
This is a reference to the full-size images in the album:
```
!AlbumFiles[myalbum]
```

Just like the `!Album` reference, it'll discover the related images. But it'll only create a an unordered list referrring to the images as available on through CloudFront. As text for the link, it'll use the decoded alt text or (if not available) use the filaname itself. This is an example of the rendered result:
```
- [This is some alt text](https://s3.example.com/myalbum/filename1.jpg)
- [More alt text. 🎉](https://s3.example.com/myalbum/filename2.jpg)
```

## Usage of script
This script usually only gets called in the pipeline during build.

### Requirements
- Have Python dependencies installed as in `../requirements.txt`.
- Provide AWS credentials for upload through `../env` (template is available as `../env.dist`).

Call the script, providing the relative path to the content directory:
```
./prepare.py ../../content
```
