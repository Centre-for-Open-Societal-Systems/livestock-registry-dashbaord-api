pipeline {
    // Docker only, no cluster or VPN access: any build agent, like the registries' build stages.
    agent any
    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
    }
    stages {
        stage('Validate and build isolated dashboard API') {
            steps { sh 'bash ci/run-isolated.sh' }
        }
    }
    post {
        always {
            junit allowEmptyResults: false, testResults: 'reports/pytest.xml'
        }
    }
}
