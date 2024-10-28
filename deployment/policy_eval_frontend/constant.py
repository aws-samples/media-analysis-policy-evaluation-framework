S3_BUCKET_NAME_PREFIX = 'video-analysis'
COGNITO_INVITATION_EMAIL_TITLE = 'Your temporary password for the ##APP_NAME##'
APP_NAME = 'Media Analysis'
SSM_INSTRUCTION_URL = 'https://github.com/aws-samples/media-analysis-policy-evaluation-framework/blob/main/access-opensearch-db.md'
COGNITO_INVITATION_EMAIL_TEMPLATE = '''

<html>
<head>
<style>
    div.WordSection1 {
        page: WordSection1;
        font-family: "Amazon Ember";
        margin: 0in;
        margin-bottom: .0001pt;
        font-size: 12.0pt;
        font-family: "Calibri", sans-serif;
    }
    span.highlight {
        font-weight: bold;
    }
</style>
</head>
<body lang="EN-US" link="#0563C1" vlink="#954F72">
<div class="WordSection1">
    <h2>
        <span class="highlight">You are invited to access the ##APP_NAME## application.
        </span>
    </h2>
    <br/>
    <p>
        <span style="font-size:13.5pt;font-family:'Amazon Ember',sans-serif;color:#333333">Click on the link below to log into the website.
        </span>
    </p>
    <p>
        <span>
            <a href="https://##CLOUDFRONT_URL##" target="_blank">https://##CLOUDFRONT_URL##</a>
        </span>
    </p>
    <p>
    <span>
        You will need the following username and temporary password provided below to login for the first time.
    </span>
    </p>
    <p>
        <span>User name:
            <b>{username}</b>
        </span>
    </p>
    <p>
        <span>Temporary password:
            <b>{####}</b>
        </span>
    </p>
    <br/>
    <p>
    <span>
    Once you log in with your temporary password, you will be required to create a new password for your account.
    </span>
    </p>
    <p>
    <span>
    After creating a new password, you can log into your ##APP_NAME## website.
    </span>
    </p>
    <br/><br/>
    <h3>Access Database</h3>
    <p>
    <span>
    For technical users, below you'll find the <b>Bastion Host ID</b> and <b>OpenSearch Domain Endpoint</b> necessary for accessing the database powering this solution.
    </span>
    </p>
    <p>
        <span>Bastion Host Id:
            <b>##BASTION_HOST_ID##</b>
        </span>
    </p>
    <p>
        <span>OpenSearch Domain Endpoint:
            <b>##OPENSEARCH_DOMAIN_ENDPOINT##</b>
        </span>
    </p>
    <p>
    <span>
    For detailed instructions on accessing the database using Amazon Session Manager, please refer to this <a href="##SSM_INSTRUCTION_URL##" target="_blank">guide</a>.
    </span>
    </p>
</div>
</body>
</html>
'''