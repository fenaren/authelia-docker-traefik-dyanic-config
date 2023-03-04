FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
VOLUME [ "/config" ]
CMD [ "python", "./app.py" ]