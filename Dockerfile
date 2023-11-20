FROM python:3.12.0-bookworm

WORKDIR /app

COPY ./requirements.lock /app/

RUN sed '/-e/d' requirements.lock > requirements.txt 

RUN --mount=type=cache,target=/root/.cache \
  pip install -r requirements.txt && rm requirements.txt

COPY ./ /app                                            

ENV PYTHONPATH="/app/src:$PYTHONPATH"

CMD ["uvicorn", "src.custom_gpts_paywall.api:app", "--host", "0.0.0.0", "--port", "80"]


