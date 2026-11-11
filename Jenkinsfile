pipeline {
    agent any

    environment {
        IMAGE_NAME = 'booknest-catalog'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Test') {
            steps {
                sh 'python3 -m pip install -r requirements.txt'
                sh 'python3 -m pytest -q'
            }
        }
        stage('Build image') {
            steps {
                sh "docker build -t ${IMAGE_NAME}:${BUILD_NUMBER} ."
            }
        }
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh "kubectl -n booknest set image deployment/catalog-service catalog=${IMAGE_NAME}:${BUILD_NUMBER}"
                sh 'kubectl -n booknest rollout status deployment/catalog-service --timeout=180s'
            }
        }
    }
}
