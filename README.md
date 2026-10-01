# Big Data apps on MacOS

This project sets up a big data applications on a Mac with ARM64 architecture/Apple silicon using Docker. It uses Makefiles to manage and run Zookeeper, Kafka, AKHQ (a GUI for Kafka), Pinot, Superset, ZooNavigator, Spark, Flink, KafkaProducer, and Hadoop services.

## Overview

This project provides a streamlined way to set up and manage a big data environment. Each service is managed from its own directory under `apps/` using a Makefile-based workflow. Docker Compose files and Makefiles ensure services run correctly, efficiently, and with proper dependency management.

### Features

- **Makefile & Docker Compose Integration**: Easily manage services using standardized Makefile commands.
- **Automatic Dependency Management**: Dependencies are started automatically as needed.
- **Health Checks**: Verify that services are healthy with a single command.
- **Orphan Container Cleanup**: Remove orphan containers before starting new ones.
- **Network Management**: All services run on the same Docker network.
- **Persistent Data & Configs**: Data and configuration are stored in `app-data/` and `configs/`.

## Prerequisites

- Docker or Docker Desktop
- Bash

## Setup Instructions

### 1. Clone the Repository
```sh
git clone https://github.com/your-repo/big-data-mac-arm64-setup.git
cd big-data-mac-arm64-setup
```




## Running the Services (Makefile-based)

Each service is managed from its own directory under `apps/` using Makefile commands. The Makefile system will automatically start dependencies, run health checks, and manage containers.

### General Pattern

To start any service:
```sh
cd apps/<service>
make up
```
To stop a service:
```sh
make down
```
To check health:
```sh
make health
```
To view logs:
```sh
make logs
```

### Service-specific Instructions

#### Zookeeper
```sh
cd apps/zookeeper
make up
```
Access Admin UI: http://localhost:8081/commands, http://localhost:8082/commands, http://localhost:8083/commands

#### Kafka
```sh
cd apps/kafka
make up
```

#### AKHQ (Kafka UI)
```sh
cd apps/akhq
make up
```
Access UI: http://localhost:9093

#### Pinot
```sh
cd apps/pinot
make up
```
Access UI: http://localhost:9000

#### Superset
```sh
cd apps/superset
make up
```
Access UI: http://localhost:8088

#### ZooNavigator
```sh
cd apps/zoonavigator
make up
```
Access UI: http://localhost:2180

#### Spark
```sh
cd apps/spark
make up
```
Spark Master UI: http://localhost:8072
Spark Worker UI: http://localhost:8073
Place job JARs in `app-data/spark/local-jars/`
To run a Spark job:
```sh
docker exec -it spark-master spark-submit \
    --master spark://spark-master:7077 \
    --class com.abc.MainClass \
    --executor-memory 1G \
    --total-executor-cores 1 \
    /opt/spark/local-jars/yourjar.jar
```
For remote debugging, add the appropriate `--conf` options as in the previous README.

#### Flink
```sh
cd apps/flink
make up
```
Flink Job Manager UI: http://localhost:8074
To enable flame graphs, set `rest.flamegraph.enabled: true` in `configs/flink/flink-conf.yaml`

#### KafkaProducer
```sh
cd apps/kafkaproducer
make up
```
Place message files in `app-data/kafkaproducer/messages/`

#### Hadoop
```sh
cd apps/hadoop
make up
```
if you're running for the first time use
```sh
cd apps/hadoop
make up-reset
```

Namenode UI: http://localhost:9870
ResourceManager UI: http://localhost:8088


## Additional Information

- **Health Checks:** Use `make health` in each service directory.
- **Dependencies:** Handled automatically; you do not need to start dependencies manually.
- **Network:** All services are on the same Docker network for seamless communication.
- **Logs:** Use `make logs` for troubleshooting.
- **Volumes:** Data and configs are persisted in `app-data/` and `configs/`.
- **.gitignore:** Add `/app-data/` and `/configs/` to `.gitignore` to avoid committing data/configs.

By following these instructions, you can set up and manage a big data environment on your Mac with ease using Makefile commands.

---

### Summary Table

| Service         | Directory         | Start Command           | UI/Port Example         | Depends On         |
|-----------------|------------------|-------------------------|------------------------|--------------------|
| Zookeeper       | zookeeper        | `make up`               | 8081/8082/8083         | -                  |
| Kafka           | kafka            | `make up`               | 9092                   | Zookeeper          |
| AKHQ            | akhq             | `make up`               | 9093                   | Kafka              |
| Pinot           | pinot            | `make up`               | 9000                   | Zookeeper          |
| Superset        | superset         | `make up`               | 8088                   | Pinot, Postgres    |
| ZooNavigator    | zoonavigator     | `make up`               | 2180                   | Zookeeper          |
| Spark           | spark            | `make up`               | 8072, 8073, 18080      | Hadoop, Zookeeper  |
| Flink           | flink            | `make up`               | 8074                   | Hadoop, Zookeeper  |
| KafkaProducer   | kafkaproducer    | `make up`               | 8085                   | Kafka              |
| Hadoop          | hadoop           | `make up`               | 9870, 8088             | Zookeeper          |

## License

Contributions are welcome! Please fork the repository and submit a pull request for review.
This project is licensed under the MIT License - see the [LICENSE](LICENSE.txt) file for details.
