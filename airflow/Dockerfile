FROM apache/airflow:3.3.2-python3.12

# pipeline ใช้ pandas 3 / SQLAlchemy 2 ซึ่งอาจชนกับ dependency ของ Airflow เอง
# จึงลงไว้ใน venv แยก แล้วให้ task เรียก /opt/pipeline-venv/bin/python
USER root
RUN mkdir /opt/pipeline-venv && chown airflow: /opt/pipeline-venv
USER airflow
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/pipeline-venv \
    && /opt/pipeline-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
