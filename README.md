In this Code Pattern, we provide a long-running script that can monitor a folder for changes. As images are copied to the folder, they will then be automatically uploaded to be analyzed by a visual recognition service. This solution is primarily geared towards utility and communications companies that use drones to inspect their equipment. As the inspection footage is copied from the drone storage, the videos are split up into frames, and each individual frame is analyzed. The recognized class/object (ex. bad insulator, broken couplings, missing nuts), confidence score, heatmap, and video timestamp can then be stored in a CSV file. This CSV file is compatible with our previous code pattern [here](https://github.com/IBM/visual-insights-table), which renders the analysis results in a dashboard.

<img src="https://i.imgur.com/ikvffft.png"  />

### Flow:

1. User inserts storage card from drone/camera
2. User drags images to specified folder.
3. Script recognizes new images have been added to folder
4. Script posts new Images to IBM Visual Insights <!-- Maximo Visual Inspection APIs -->
5. Analysis results are returned to Python
6. Results are parsed and written to a CSV file
7. CSV file is loaded into web application
8. User is able to view and filter inference info in application

### Prerequisites:

- Python 3 + pip
- IBM Visual Insights

Install the ffmpeg-python package
```
python3 -m pip install ffmpeg-python
```

To analyze images, you will need to train an inference model within your Visual Insights instance before running this script. If training a classification model, we recommend using the pattern [here](https://github.com/IBM/visual-insights-data-sync). The referenced pattern uses a similar script to train a model as images are added to folders.

After training a model, it will also need to be [deployed](https://www.ibm.com/support/knowledgecenter/SSRU69_1.2.0/base/vision_deploy.html).

By default, inference results will be temporarily stored in the Visual Insights server. We can instead persist the uploaded images and inference results in a dataset. When deploying the model, be sure to check the "Advanced Options" in the upper right, and select "Save" in the "Inference Results" section.

<img src="https://i.imgur.com/p9nYS9m.png" />



<!-- - Maximo Visual Inspector -->

## Steps:
1. [Clone the repo](#1-clone-the-repo)
2. [Populate configuration file with service credentials / model name](#2-populate-configuration-file)
3. [Test script](#3-test-script)
4. [Load CSV in webapp (optional)](#4-load-csv)


## 1. Clone the repo
```
git clone https://github.com/IBM/automated-visual-analysis
```

## 2. Populate configuration file

After a model is trained and deployed, populate a configuration file using the example below. You will need to provide your login credentials, url of the server, model name, and list of folders that will be monitored by the script.

```
{
  "credentials": {
    "endpoint": "<url>",
    "port": "<port>",
    "username": "<username>",
    "password": "<password>"
  },
  "threshold": {
    "upload": 1
  },
  "time": 5,
  "model": {
    "name": "<model_name>"
  },
  "folders": [
    "<path to images>"
  ]
}
```

Once you have filled out the fields, save the file as `configuration.json`.

## 3. Start the script

```
python3 infer_script.py
```

You should see output like so
```
analyzing images
setting token e99a2724-35b4-49fd-8724-5f6a15b08aae
Observing files in ['/tmp/script_monitor/']
```

Next, copy files to the defined path (`/tmp/script_monitor` in this case). The script should then have the following output, indicating that new images have been recognized, and will be analyzed after 5 seconds.

```
2020-06-16 12:17:31 - Moved file: from /tmp/download.png to /tmp/script_monitor/download1.png
2020-06-16 12:17:31 - Modified directory: /tmp/script_monitor/
>>>>>>>>>> new file added <<<<<<<<<<<<
/tmp/script_monitor/download1.png
files exceed threshold, starting upload timer
waiting for 5.0 seconds to upload files
>>>>>> finished handling file /tmp/script_monitor/download1.png <<<<<<<
```

<!-- Copy images to folder to trigger image inference. Drag and drop the images to the folder you've set in the configuration file. -->

This particular model analyzes the images using an object detection algorithm. So, our output CSV will have the following format.

Object Detection
- URL
- Analysis Type
- Coordinates of the bounding boxes
- Objects detected (delimited by `|`)
- Confidence score of each object

<!-- ```
https://<url>/uploads/temp/4c436fa6-188f-4fdf-8e0f-9e46b79b0b1a/35c5a552-3e63-4e56-9b63-d06e8893c94f.png,Object Detection,643-365-681-493|790-544-1057-859,Green|Red,0.963|0.999
``` -->

Classification
- URL
- Analysis Type
- Heatmap of image section that matches class
- Detected Class
- Confidence score


## 4. Load CSV in dashboard (Optional)
After storing the results in a CSV file, we can then view them in a dashboard. The codebase for this dashboard is provided in a previous pattern.

```
git clone -b drone https://github.com/IBM/visual-insights-table
cd visual-insights-table
cd frontend
npm install
npm run serve
```

Navigate to the dashboard in your browser at [http://localhost:8080](http://localhost:8080).

Then, click "Import CSV file"
<img src="https://i.imgur.com/NfIeVS3.png" />

Drag and drop your CSV file to the zone, and each inferred image should show up in the table like so

<img src="https://i.imgur.com/Q5mNvLh.png" />


Clicking on a thumbnail image will show an enlarged image with the classified zones highlighted. Object detection results are indicated by bounding boxes. Classification results are represented through a heatmap overlay.

<img src="https://i.imgur.com/D9cIgMl.png" />
