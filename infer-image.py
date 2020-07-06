import sys
import time
import logging
import requests
import json
from datetime import datetime
from datetime import date
import time
from threading import Timer
from threading import Thread
import threading
import zipfile
import os

import csv
import base64
import ffmpeg
import glob
import re


from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler


from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

green_text = "\033[1;32;40m"
white_text = '\033[0m' #"\033[1;37;40m"
yellow_text = "\033[1;33;40m"
red_text = '\033[91m'
blue_text = '\033[94m'

# load config file
f = open('./configuration.json')
config = json.load(f)
upload_threshold = config['threshold']['upload']

# dataset_name = config['dataset']['name']

if 'action' in config['model'].keys():
    action = config['model']['action'].lower()
else:
    action = None

base_url = config['credentials']['endpoint']

# Paiv calls
def get_token(config):
    credentials = config['credentials']
    body = {
        'grant_type':'password',
        'username': config['credentials']['username'],
        'password': config['credentials']['password']
    }
    url = config['credentials']['endpoint'] + '/api/tokens' # + config['credentials']['port']
    print(f'requesting token')
    headers = {'content-type': 'application/json'}
    r = requests.post(url, json=body, headers=headers, verify=False)
    if r.status_code == 200:
        res = r.json()
        global token
        token = res['token']
        print(f"setting token {token}")
        return token
    else:
        print(f"{red_text}failure getting token HTTP {r.status_code}. Please correct credentials in config file.")
        exit()

models = []
def get_models():
    global models
    r = requests.get(f"{base_url}/api/trained-models", headers=headers, verify=False)
    if r.status_code == 200:
        models = r.json()
        return models
    else:
        print(f"error getting models")
        print(r.status_code)

def infer_images():
    # credentials = config['credentials']
    # files = [('file', open('report.xls', 'rb')), ('file', open('report2.xls', 'rb'))]
    global files_to_upload
    # global headers
    global token
    global model_id
    headers = {
        'X-Auth-Token': token
    }
    csv_file = open('out.csv', 'w+')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    url = config['credentials']['endpoint'] + 'api/dlapis/' + model_id #config['model']['name']
    results = []
    csv_headers = ['ImageURL', "AnalysisType", "Heatmap/Boxes", 'Class', 'Score', 'Time', "ID"] #
    csv_writer.writerow(csv_headers)
    for f in files_to_upload:
        # files = ('file', open(f, 'rb').read())
        # files = open(f, 'rb').read()
        body = {
            # "files": files[1],
            "containHeatMap": "true"
        }
        print(f"{green_text} posting to url {url}{white_text}")
        r = requests.post(url, files=[('files', open(f, 'rb'))], data=body, headers=headers, verify=False)
        # r = requests.post(url, files=files, headers=headers, verify=False)
        if r.status_code == 200:
            res = r.json()
            results.append(res)
            print(res['classified'])
            # res['classified']
            result = res['classified']
            # if (isinstance(res['classified'], dict)):
            if 'heatmap' in res.keys():
                # classification
                print("inferring classification model")
                if isinstance(res['classified'], dict):
                    cls = list(res['classified'].keys())[0]
                    score = res['classified'][cls]
                else:
                    cls = res['classified'][0]['name']
                    score = res['classified'][0]['confidence']
                print(res['classified'])
                url_post = res['imageUrl'].split('/uploads')[1]
                image_url = base_url + '/uploads/' + url_post
                row = [
                    # base64.standard_b64encode(res['heatmap'].encode()),
                    image_url,
                    "Classification",
                    res['heatmap'].split(',')[1],
                    cls,
                    score
                ]
                if '_frame_' in f:
                    frames = int(re.search('[0-9]+', f.split('_frame_')[1]).group(0))
                    print(f"processing frame {frames}")
                    fps = 24
                    minutes = int(frames / fps)
                    seconds = frames % fps
                    if minutes < 10:
                        minutes = f"0{minutes}"
                    if seconds < 10:
                        seconds = f"0{seconds}"
                    row.append(f"{minutes}:{seconds}")
                # row.append()
            else: #(isinstance(result, list)):
                # {'webAPIId': '4c436fa6-188f-4fdf-8e0f-9e46b79b0b1a', 'imageUrl': 'http://vision-v120-prod-service:9080/vision-v120-prod-api/uploads/temp/4c436fa6-188f-4fdf-8e0f-9e46b79b0b1a/4c492b15-5ef2-4c16-9081-dfb5392cfbcd.png', 'imageMd5': 'b3dcfd4ac6757a6e688d84e91585ab16', 'classified': [{'confidence': 0.963, 'ymax': 681, 'label': 'Green', 'image_id': '4c492b15-5ef2-4c16-9081-dfb5392cfbcd.png', 'xmax': 643, 'xmin': 365, 'ymin': 493}, {'confidence': 0.999, 'ymax': 1057, 'label': 'Red', 'image_id': '4c492b15-5ef2-4c16-9081-dfb5392cfbcd.png', 'xmax': 790, 'xmin': 544, 'ymin': 859}], 'result': 'success'}
                print("inferring obj model")
                # object detect
                # score = result[cls]
                # ['ImageURL', "Heatmap", 'Class', 'Score', 'Time'] #
                classes = ""
                coords = ""
                scores = ""
                for obj in result:
                    # if 'label' in obj.keys():
                    classes += obj['label'] + '|'
                    coords += f"{obj['xmax']}-{obj['xmin']}-{obj['ymax']}-{obj['ymin']}" + '|'
                    scores += str(obj['confidence']) + '|'
                url_post = res['imageUrl'].split('/uploads')[1]
                image_url = base_url + '/uploads/' + url_post
                row = [
                    # base64.standard_b64encode(res['heatmap'].encode()),
                    image_url,
                    "Object Detection",
                    coords[:-1],
                    classes[:-1],
                    scores[:-1]
                ]
                print("writing row to csv file")
                csv_writer.writerow(row)
                '''
                # individual row each object
                for obj in result:
                    cls = obj['label']
                    coords = f"{obj['xmax']}-{obj['xmin']}-{obj['ymax']}-{obj['ymin']}"
                    score = obj['confidence']
                    url_post = res['imageUrl'].split('/uploads')[1]
                    image_url = base_url + '/uploads/' + url_post
                    row = [
                        # base64.standard_b64encode(res['heatmap'].encode()),
                        image_url,
                        "Object Detection",
                        coords,
                        cls,
                        score
                    ]
                    print("writing row to csv file")
                    csv_writer.writerow(row)
                '''
            # else:
                # row.append(None)
                # print("unexpected response")
                # row = [None]
            print("writing csv file")
            csv_writer.writerow(row)
        else:
            print(f"failure inferring image HTTP {r.status_code}")
            print(r.text)
    csv_file.close()
    files_to_upload = []
    return results

def start_upload_timer():
    # We're using an timer in case the user adds more files to any of the subfolders after the threshold is met
    # This will give the user a buffer of x seconds to add more files. Timer is reset every time the
    upload_thread = list(filter(lambda t: (t.name == 'upload_timer'), threading.enumerate()))
    if upload_thread: #'upload_timer' in [t.name == 'upload_timer' for t in threading.enumerate()]:
        print("more files added, resetting upload timer")
        upload_thread[0].cancel()
    else:
        print("files exceed threshold, starting upload timer")
    upload_timer_wait_time = 5.0
    print(f"waiting for {upload_timer_wait_time} seconds to upload files")
    upload_timer = Timer(upload_timer_wait_time, infer_images) #, args=[files_to_upload], name="upload_timer")
    upload_timer.name = 'upload_timer'
    upload_timer.start()

total_file_count = 0
file_upload_count = 0
file_train_count = 0

token = get_token(config)
headers = {
    'X-Auth-Token': token
}

files_to_upload = []

# with open('out.csv', mode='w+') as csv_file:
#     csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)


models = get_models()
try:
    selected_model = [ m for m in models if (m['name'] == config['model']['name']) and (m['deployed'] == 1 ) ]
    model = selected_model[0]
    model_id = model['_id']
except:
    print(f"{red_text}Model {config['model']['name']} not found. Please correct name/id in config file and restart script. {white_text}")
    exit()

# infer_images()


class Event(LoggingEventHandler):
    # file_upload_count = 0
    # file_train_count = 0
    def on_created(self, event):
        global total_file_count
        global file_upload_count
        global file_train_count
        global files_to_upload
        print(">>>>>>>>>> new file added <<<<<<<<<<<<")
        print(event.src_path)
        split_path = event.src_path.split('/')
        filename = split_path[-1]
        category = split_path[-2]
        # if category not in files_to_upload.keys():
        #     files_to_upload[category] = []
        # image_type = filename.split('.')[-1]
        if '.' not in filename:
            return
        name, image_type = filename.split('.')
        if image_type.lower() not in ['jpg', 'jpeg', 'png', 'mp4']:
            print(f"skipping unsupported media type {image_type}")
            return
        if image_type in ['mp4']:
            # split into frames
            # filename = "test_video.mp4"
            # name, image_type = filename.split('.')
            # TODO, this is mostly only necessary for classification. Object detection *should* do the split already
            print(f"{green_text} splitting mp4 file {white_text}")
            frame_output_dir = config['folders'][0]
            fps = float(1 / float(config['frame_interval']))
            # ffmpeg.input(config['folders'][0] + filename).filter('fps', fps=fps, round='up').output( frame_output_dir + name + "_frame_%d.png").run()
            ffmpeg.input(config['folders'][0] + filename).filter('fps', fps=fps).output( frame_output_dir + name + "_frame_%d.png").run()
            frames = glob.glob(frame_output_dir + name + '*.png')
            for frame in frames:
                files_to_upload.append(frame)
                total_file_count += 1
                file_upload_count += 1
                file_train_count += 1
            print(files_to_upload)
        else:
            files_to_upload.append(event.src_path)
            total_file_count += 1
            file_upload_count += 1
            file_train_count += 1
        print(f'upload: {file_upload_count} / {upload_threshold}')
        print(f'total_file_count: {total_file_count}')
        if file_upload_count > upload_threshold:
            # upload_in_progress = True
            start_upload_timer()

        print(f">>>>>> finished handling file {event.src_path} <<<<<<<")
        # files.append(event.src_path)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    # path = config['folders']
    event_handler = Event()
    observer = Observer()
    if config['folders']:
        for folder in config['folders']:
            observer.schedule(event_handler, folder, recursive=True)
    else:
        path = sys.argv[1] if len(sys.argv) > 1 else '.'
        observer.schedule(event_handler, path, recursive=True)
    observer.start()
    print(f"{yellow_text} Observing files in {config['folders']} {white_text}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
