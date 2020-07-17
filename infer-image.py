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

import asyncio
import aiohttp

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

rows_dict = {}

# dataset_name = config['dataset']['name']

base_url = config['credentials']['endpoint']

# Paiv calls
headers = None
def get_token(config):
    global headers
    credentials = config['credentials']
    body = {
        'grant_type':'password',
        'username': config['credentials']['username'],
        'password': config['credentials']['password']
    }
    url = config['credentials']['endpoint'] + '/api/tokens' # + config['credentials']['port']
    print(f'requesting token')
    token_headers = {'content-type': 'application/json'}
    r = requests.post(url, json=body, headers=token_headers, verify=False)
    if r.status_code == 200:
        res = r.json()
        global token
        token = res['token']
        print(f"setting token {token}")
        headers = {
            'X-Auth-Token': token
        }
        return token
    else:
        print(f"{red_text}failure getting token HTTP {r.status_code}. Please correct credentials in config file.")
        exit()

def get_models():
    global models
    r = requests.get(f"{base_url}/api/trained-models", headers=headers, verify=False)
    if r.status_code == 200:
        models = r.json()
        return models
    else:
        print(f"error getting models")
        print(r.status_code)



def get_datasets():
    r = requests.get(f"{base_url}/api/datasets", headers=headers, verify=False)
    if r.status_code == 200:
        datasets = r.json()
        return datasets
        global ds_ids
        ds_ids = {}
        for d in datasets:
            ds_ids[d['name']] = {
                "_id": d['_id'],
                "categories": []
            }
        return ds_ids
    else:
        print(f"error getting datasets")
        print(r.status_code)

def get_dataset_files(dataset_id):
    r = requests.get(f"{base_url}/api/datasets/{dataset_id}/files", headers=headers, verify=False)
    if r.status_code == 200:
        dataset_files = r.json()
        return dataset_files
    else:
        print("error retreiving dataset files")
        print(r.status_code)
        return []

def get_output_ds_id():
    r = requests.get(f"{base_url}/api/webapis", headers=headers, verify=False)
    if r.status_code == 200:
        # grab all models that save to output ds
        # TODO, may need user to provide dataset name if not provided
        model = [m for m in r.json() if (m['save_inference'] and (m['name'] == config['model']['name']) )]
        if len(model) > 0:
            return model[0]['save_inference']
        else:
            print("no output dataset found for specified model")
    else:
        print("error retreiving dataset files")
        print(r)
        return []



def get_file_labels(dataset_id, file_id):
    # print(f"{base_url}/api/datasets/{dataset_id}/files/{file_id}/labels")
    # /datasets/{dsid}/files/{fid}/object-labels
    # /datasets/{dataset_id}/object-labels
    # r = requests.get(f"{base_url}/api/datasets/{dataset_id}/files/{file_id}/labels", headers=headers, verify=False)
    r = requests.get(f"{base_url}/api//datasets/{dataset_id}/object-labels", headers=headers, verify=False)
    if r.status_code == 200:
        print("labels retrieved")
        labels = r.json()
        return labels
    else:
        print("error retreiving labels from dataset")
        return []

# only for videos
def get_inferences():
    r = requests.get(f"{base_url}/api/inferences", headers=headers, verify=False)
    if r.status_code == 200:
        print("inferences retrieved")
        inferences = r.json()
        return inferences
    else:
        print("error retreiving labels from dataset")
        return []

class Row:
    url = None
    type = None
    annotation = None
    cls = None
    score = None
    filename = None


# data = {
#     "containHeatMap": "true",
#     'files': open(f, 'rb')
# }

async def post(file):
    headers = {
        'X-Auth-Token': token
    }
    url = config['credentials']['endpoint'] + 'api/dlapis/' + model_id #config['model']['name']
    print(f"posting {file} to {url}")
    async with aiohttp.ClientSession() as session:
        # async with requests.post(url, headers=headers, verify=False, data={"containHeatMap": "true", 'files': open(file, 'rb') } ) as response:
        async with session.post(url, headers=headers, verify_ssl=False, data={"containHeatMap": "true", 'files': open(file, 'rb') } ) as response:
            assert response.status == 200
            print(f"received results from {file}")
            # await response.json()
            # return await process_inference(response.json())
            return await response.json()
            # process_inference(response.json())


# get image inference results
def infer_images_async():
    # loop = asyncio.get_event_loop()
    global rows_dict
    global files_to_upload
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    files_to_upload = list(set(files_to_upload))
    coroutines = [post(image) for image in files_to_upload]
    image_results = loop.run_until_complete(asyncio.gather(*coroutines))
    loop.close()
    # for result in image_results:
    print(f"loop finished, processing {len(image_results)} results and {len(files_to_upload)} files ------")
    for idx in range(0, len(image_results) - 1):
        print(f"processing results for {files_to_upload[idx]}")
        process_inference(image_results[idx], files_to_upload[idx])
        # process_inference(result)
    print("loop finished, processing ------")
    if output_ds:
        map_image_urls()
    write_inferences_csv(rows_dict)
    rows_dict = {}
    return

def write_inferences_csv(inference_results):
    print("writing to out.csv")
    csv_file = open('out.csv', 'w+')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_headers = ['ImageURL', "InferenceType", "Heatmap/Boxes", 'Class', 'Score', 'Time'] #, "ID"] #
    csv_writer.writerow(csv_headers)
    for img in rows_dict.keys():
        csv_writer.writerow(rows_dict[img])
    csv_file.close()


def map_image_urls():
    print("output dataset exists, correcting image url")
    global rows_dict
    files = get_dataset_files(output_ds)
    print("files retrieved")
    row_files = rows_dict.keys()
    print(f"comparing files to {row_files}")
    for file in files:
        if file['original_file_name'] in row_files:
            print(f"updating image url for {file['file_name']}")
            image_url = f"{base_url}/uploads/{config['credentials']['username']}/datasets/{output_ds}/files/{file['file_name']}"
            rows_dict[file['original_file_name']][0] = image_url
    # return rows_dict

def process_inference(result, original_filename):
    # image_url = build_image_url(result)
    global rows_dict
    image_url = result['imageUrl']
    filename = image_url.split('/')[-1]
    if 'heatmap' in result.keys():
        analysis_type = "Classification"
        if 'classified' in result.keys():
            classes, heatmap_coords, score = parse_classification_inference(result['classified'])
        else:
            classes, heatmap_coords, score = parse_classification_inference(result)
    else:
        analysis_type = "ObjectDetection"
        # classes, heatmap_coords, score = parse_object_inference(result)
        if 'classified' in result.keys():
            classes, heatmap_coords, score = parse_object_inference(result['classified'])
        else:
            classes, heatmap_coords, score = parse_object_inference(result)
    print(f"processing inference {original_filename}")
    video_time = get_time(original_filename)
    # row = [image_url, analysis_type, heatmap_coords, classes, score]
    rows_dict[filename] = [image_url, analysis_type, heatmap_coords, classes, score, video_time]
    # return row



def build_image_url(result):
    # returned "ImageURL" is for temporary image
    # filename = result['image_id']
    image_url = result['imageUrl']
    filename = image_url.split('/')[-1]
    if output_ds:
        # TODO, heatmap is not stored in vis insights, so have to keep in csv for now
        endpoint = f"/{config['credentials']['username']}/datasets/{output_ds}/files/{filename}"
    elif 'output_ds' in config['model']:
        endpoint = f"/{config['credentials']['username']}/datasets/{config['model']['output_ds']}/files/{filename}"
    else:
        endpoint = image_url.split('/uploads')[1]
    image_url = base_url + '/uploads/' + endpoint
    return image_url


def get_time(f):
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
        # row.append(f"{minutes}:{seconds}")
        return f"{minutes}:{seconds}"


# get rows
def parse_classification_inference(res):
    # classification
    if isinstance(res['classified'], dict):
        # different response btwn 1.2 and 1.3
        cls = list(res['classified'].keys())[0]
        score = res['classified'][cls]
    else:
        cls = res['classified'][0]['name']
        score = res['classified'][0]['confidence']
    return (cls, res['heatmap'].split(',')[1], score)

def parse_object_inference(result):
    # object
    classes = ""
    coords = ""
    scores = ""
    for obj in result:
        # if 'label' in obj.keys():
        classes += obj['label'] + '|'
        coords += f"{obj['xmax']}-{obj['xmin']}-{obj['ymax']}-{obj['ymin']}" + '|'
        scores += str(obj['confidence']) + '|'
    return (classes[:-1], coords[:-1], scores[:-1])


def infer_image(file_path):
    headers = {
        'X-Auth-Token': token
    }
    url = config['credentials']['endpoint'] + 'api/dlapis/' + model_id #config['model']['name']
    r = requests.post(url, files=[('files', open(file_path, 'rb'))], data=body, headers=headers, verify=False)
    if r.status_code == 200:
        return r.json()


def infer_images():
    # credentials = config['credentials']
    # files = [('file', open('report.xls', 'rb')), ('file', open('report2.xls', 'rb'))]
    global files_to_upload
    # global headers
    headers = {
        'X-Auth-Token': token
    }
    csv_file = open('out.csv', 'w+')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    url = config['credentials']['endpoint'] + 'api/dlapis/' + model_id #config['model']['name']
    results = []
    csv_headers = ['ImageURL', "AnalysisType", "Heatmap/Boxes", 'Class', 'Score', 'Time', "ID"] #
    csv_writer.writerow(csv_headers)
    rows_dict = {}
    session = requests.Session()
    for f in list(set(files_to_upload)):
        # files = ('file', open(f, 'rb').read())
        # files = open(f, 'rb').read()
        body = {
            # "files": files[1],
            "containHeatMap": "true"
        }
        print(f"{green_text} posting to url {url}{white_text}")

        # r = requests.post(url, files=[('files', open(f, 'rb'))], data=body, headers=headers, verify=False)
        r = session.post(url, files=[('files', open(f, 'rb'))], data=body, headers=headers, verify=False)
        if r.status_code == 200:
            res = r.json()
            results.append(res)
            print(res['classified'])
            # res['classified']
            result = res['classified']
            # if (isinstance(res['classified'], dict)):
            print(res)
            # TODO, extract model type from json instead of checking for heatmap
            if 'heatmap' in res.keys():
                analysis_type = "Classification"
            else:
                analysis_type = "ObjectDetection"
            if (output_ds) and (analysis_type == "ObjectDetection"):
                # TODO, heatmap is not stored in vis insights, so have to keep in csv for now
                if len(result) > 0:
                    print(result)
                    filename = res['image_id']
                url_post = f"/{config['credentials']['username']}/datasets/{dataset_id}/files/{filename}"
            elif ('output_ds' in config['model']) and (analysis_type == "Object Detection"):
                # TODO, add
                url_post = f"/{config['credentials']['username']}/datasets/{config['model']['output_ds']}/files/{filename}"
            else:
                url_post = res['imageUrl'].split('/uploads')[1]
            image_url = base_url + '/uploads/' + url_post
            # extract new filename from payload
            filename = image_url.split('/')[-1]
            if analysis_type == "Classification":
                # classification
                if isinstance(res['classified'], dict):
                    # different response btwn 1.2 and 1.3
                    cls = list(res['classified'].keys())[0]
                    score = res['classified'][cls]
                else:
                    cls = res['classified'][0]['name']
                    score = res['classified'][0]['confidence']
                print(res['classified'])
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
                rows_dict[filename] = row
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
                row = [
                    # base64.standard_b64encode(res['heatmap'].encode()),
                    image_url,
                    "Object Detection",
                    coords[:-1],
                    classes[:-1],
                    scores[:-1]
                ]
                #
                rows_dict[filename] = row
                # csv_rows.append(row)
        else:
            print(f"failure inferring image HTTP {r.status_code}")
            print(r.text)

    if output_ds:
        print("output dataset exists, correcting image url")
        files = get_dataset_files(output_ds)
        row_files = rows_dict.keys()
        for file in files:
            if file['original_file_name'] in row_files:
                image_url = f"{base_url}/uploads/{config['credentials']['username']}/datasets/{output_ds}/files/{file['file_name']}"
                print(f"updating image url for {file['file_name']}")
                rows_dict[file['original_file_name']][0] = image_url

            # i = filter(lambda inf: inf['original_filename'] == filename, files)
    # for row in csv_rows:
    for filename in rows_dict:
        print("writing row to csv")
        csv_writer.writerow(rows_dict[filename])
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
    # upload_timer = Timer(upload_timer_wait_time, infer_images) #, args=[files_to_upload], name="upload_timer")
    upload_timer = Timer(upload_timer_wait_time, infer_images_async) #, args=[files_to_upload], name="upload_timer")
    upload_timer.name = 'upload_timer'
    upload_timer.start()

total_file_count = 0
file_upload_count = 0
file_train_count = 0

token = get_token(config)

files_to_upload = []
models = get_models()
try:
    selected_model = [ m for m in models if (m['name'] == config['model']['name']) and (m['deployed'] == 1 ) ]
    model = selected_model[0]
    model_id = model['_id']
except:
    print(f"{red_text}Model \"{config['model']['name']}\" not found. Please correct name/id in config file and restart script. {white_text}")
    exit()

output_ds = get_output_ds_id()
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
            if '/' != config['folders'][0][-1]:
                frame_output_dir += "/"
            fps = 1.0 / float(config['frame_interval'])
            # ffmpeg.input(config['folders'][0] + filename).filter('fps', fps=fps, round='up').output( frame_output_dir + name + "_frame_%d.png").run()
            ffmpeg.input(f"{config['folders'][0]}/{filename}").filter('fps', fps=fps).output( frame_output_dir + name + "_frame_%d.png").run()
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
