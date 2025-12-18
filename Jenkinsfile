pipeline {
    agent any

    options {
        buildDiscarder(logRotator(
            numToKeepStr: '10',
            daysToKeepStr: '7',
            artifactNumToKeepStr: '5'
        ))
        timeout(time: 30, unit: 'MINUTES')
    }

    environment {
        IMAGE_NAME = 'video-backend-py'
        APP_NAME = 'video-backend-py'
    }

    stages {

        stage('Checkout') {
            steps {
                deleteDir() // 删除工作空间
                checkout scm // 检出代码
            }
        }
        stage('Prepare') {
            steps {
                script {
                    // 下载并解压 FFmpeg
                    sh '''
                        FFMPEG_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
                        FFMPEG_ARCHIVE="ffmpeg.tar.xz"
                        FFMPEG_DIR="ffmpeg-build"
                        
                        echo "下载 FFmpeg..."
                        curl -L -o ${FFMPEG_ARCHIVE} ${FFMPEG_URL}
                        
                        echo "解压 FFmpeg..."
                        mkdir -p ${FFMPEG_DIR}
                        tar -xf ${FFMPEG_ARCHIVE} -C ${FFMPEG_DIR} --strip-components=1
                        
                        echo "复制 FFmpeg 二进制文件..."
                        cp ${FFMPEG_DIR}/bin/ffmpeg ./ffmpeg
                        chmod +x ./ffmpeg
                        
                        echo "清理临时文件..."
                        rm -rf ${FFMPEG_ARCHIVE} ${FFMPEG_DIR}
                        
                        echo "验证 FFmpeg..."
                        ./ffmpeg -version
                    '''
                }
            }
        }

        stage('Build') {
            steps {
                script {
                    sh """
                        docker build -t ${IMAGE_NAME}:latest .
                        docker tag ${IMAGE_NAME}:latest ${IMAGE_NAME}:${BUILD_NUMBER}
                    """
                }
            }
        }

        stage('Deploy') {
            steps {
                sh """
                    export IMAGE=${IMAGE_NAME}:latest
                    export APP_NAME=${APP_NAME}
                    docker compose down || true
                    docker compose up -d
                    docker image prune -f >/dev/null 2>&1 || true
                """
            }
        }

        stage('Health Check') {
            steps {
                sh """
                    sleep 5
                    docker exec ${APP_NAME} curl http://localhost:6869
                    docker exec ${APP_NAME} curl -sf http://localhost:6869/health | grep -q ok || exit 1
                """
            }
        }
    }

    post {
        always {
            cleanWs()
        }
        success {
            echo "✅ 构建成功！镜像: ${IMAGE_NAME}:latest"
        }
        failure {
            echo "❌ 构建失败！"
        }
    }
}