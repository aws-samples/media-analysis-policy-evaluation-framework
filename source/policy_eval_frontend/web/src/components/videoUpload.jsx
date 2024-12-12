import React from 'react';
import './videoUpload.css'
import { FetchPost } from "../resources/data-provider";
import {IsValidNumber} from "../resources/utility"
import { Button, Box, Checkbox, Link, FileUpload, Select, ExpandableSection, FormField, Input, Wizard, Container, Header, SpaceBetween, Alert, Toggle, ProgressBar, ColumnLayout, Popover, StatusIndicator} from '@cloudscape-design/components';
import { getCurrentUser } from 'aws-amplify/auth';

class VideoUpload extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: null, // null, loading, loaded
            alert: null,
            uploadFiles: [],
            numChunks: null,
            uploadedChunks: 0,

            selectedVideoSampleMode: "even",
            selectedVideoSampleIntervalS: 1,
            inputVideoSampleIntervalS: null,

            extractionSettingExpand: false,
            enableDetectText: true,
            enableDetectLabel: true,
            enableDetectModeration: true,
            enableDetectCelebrity: true,
            enableTranscription: true,
            enableShotSceneDetection: true,
            enableDetectLogo: true,
            enableImageCaption: true,
            enableSmartSample: true,
            advanceSettingExpand: false,
            enableCustomInterval: false,

            smartSampleThreshold: null,
            rekDetectLabelThredhold: null,
            rekDetectTextThredhold: null,
            rekDectectCelebrityThreshold: null,
            rekDetectModerationThreshold: null,
            shotThreshold: null,

            inputVideoSampleIntervalSValid: true,
            smartSampleThresholdValid: true,
            rekDetectLabelThredholdValid: true,
            rekDetectTextThredholdValid: true,
            rekDectectCelebrityThresholdValid: true,
            rekDetectModerationThresholdValid: true,
            shotThresholdValid: true,

            noEvaluation: false,
            selectedEvalTemplate: null,
            selectedBedrockModel: null,
            selectedBedrockKb: null,
            promptsTemplate: null,

            activeStepIndex: 0,
            fileUploadedCounter: false,
            currentUploadingFileName: null,
        };
        this.item = null;
        this.llmParameters = null;

    }

    resetState = () => {
        this.setState({
            status: null, // null, loading, loaded
            alert: null,
            uploadFiles: [],
            numChunks: null,
            uploadedChunks: 0,

            selectedVideoSampleMode: "even",
            selectedVideoSampleIntervalS: 1,
            inputVideoSampleIntervalS: null,

            extractionSettingExpand: false,
            enableDetectText: true,
            enableDetectLabel: true,
            enableDetectModeration: true,
            enableDetectCelebrity: true,
            enableTranscription: true,
            enableShotSceneDetection: true,
            enableDetectLogo: true,
            enableImageCaption: true,
            enableSmartSample: true,
            advanceSettingExpand: false,
            enableCustomInterval: false,

            smartSampleThreshold: this.llmParameters.default_settings.smart_sample_threshold_faiss,
            rekDetectLabelThredhold: this.llmParameters.default_settings.rekognition_detect_label_threshold,
            rekDetectTextThredhold: this.llmParameters.default_settings.rekognition_detect_text_threshold,
            rekDectectCelebrityThreshold: this.llmParameters.default_settings.rekognition_detect_celebrity_threshold,
            rekDetectModerationThreshold: this.llmParameters.default_settings.rekognition_detect_moderation_threshold,
            shotThreshold: this.llmParameters.default_settings.shot_detection_threshold,


            inputVideoSampleIntervalSValid: true,
            smartSampleThresholdValid: true,
            rekDetectLabelThredholdValid: true,
            rekDetectTextThredholdValid: true,
            rekDectectCelebrityThresholdValid: true,
            rekDetectModerationThresholdValid: true,
            shotThresholdValid: true,

            noEvaluation: false,
            selectedEvalTemplate: null,
            selectedBedrockModel: {label: this.llmParameters.bedrock_model_ids[0].name, value: this.llmParameters.bedrock_model_ids[0].value},
            selectedBedrockKb: null,
            promptsTemplate: null,

            activeStepIndex: 0,
            fileUploadedCounter: false,
            currentUploadingFileName: null
        });
        this.uploadTimer = null;
    }

    async componentDidMount() {
        if (this.llmParameters === null) {
            fetch('./llm-eval-template.json')
            .then(response => response.json())
            .then(data => {
                this.llmParameters = data;
                this.setState({
                    selectedVideoSampleIntervalS: 1,
                    inputVideoSampleIntervalS: 1,
                    selectedBedrockModel: {label: data.bedrock_model_ids[0].name, value: data.bedrock_model_ids[0].value},
                    smartSampleThreshold: data.default_settings.smart_sample_threshold_faiss,
                    rekDetectLabelThredhold: data.default_settings.rekognition_detect_label_threshold,
                    rekDetectTextThredhold: data.default_settings.rekognition_detect_text_threshold,
                    rekDetectModerationThreshold: data.default_settings.rekognition_detect_moderation_threshold,
                    rekDectectCelebrityThreshold: data.default_settings.rekognition_detect_celebrity_threshold,
                    shotThreshold: data.default_settings.shot_detection_threshold,
                });
            })
            .catch(error => {
                console.error('Error fetching llm template:', error);
            });
        }
    }


    handleNavigate = e => {
        if(e.detail.requestedStepIndex === 1) {
            if (this.state.uploadFiles.length === 0) {
                this.setState({alert: 'Please select a video file to continue.'});
                return;
            }
        }
        else if(e.detail.requestedStepIndex === 2) {
            if ((this.state.enableCustomInterval && !this.state.inputVideoSampleIntervalSValid) 
                || !this.state.smartSampleThresholdValid 
                || !this.state.rekDetectLabelThredholdValid 
                || !this.state.rekDetectTextThredholdValid 
                || !this.state.rekDectectCelebrityThresholdValid 
                || !this.state.rekDetectModerationThresholdValid
                || !this.state.shotThresholdValid
            ) {
                    this.setState({alert: "Ensure the settings are correct before proceeding to the next step."});
                    return;
                }
            else {
                this.setState({alert: null});
            }
        }
        this.setState({aler: null, activeStepIndex: e.detail.requestedStepIndex})
    }

    async handleSumbitTask () {
        for (let i = 0; i < this.state.uploadFiles.length; i++) {
            this.generatePresignedUrls(this.state.uploadFiles[i]);
        }
    }

    generatePresignedUrls (file) {
        // Wait if other file is uploading
        if (this.state.currentUploadingFileName !== null)
            setTimeout(() => {
                console.log(`Waiting`);
            }, 1000); 

        this.setState({currentUploadingFileName: file.name})
        //console.log(fileName);
        const fileSize = file.size;
        const numChunks = Math.ceil(fileSize / (5 * 1024 * 1024));
        this.setState({numChunks: numChunks});  

        this.setState({status: "generateurl"});
        FetchPost("/extraction/video/manage-s3-presigned-url", {"FileName": file.name, "NumParts": numChunks, "Action": "create"})
            .then((data) => {
                  //console.log(resp);
                  if (data.statusCode !== 200) {
                      this.setState( {status: null, alert: data.body});
                  }
                  else {
                      if (data.body !== null) {
                          return this.uploadFile({
                            taskId: data.body.TaskId,
                            uploadS3Url: data.body.UploadUrl,
                            uploadedS3Bucket: data.body.S3Bucket,
                            uploadedS3KeyVideo: data.body.S3Key,
                            status: null,
                            alert: null,
                            uploadId: data.body.UploadId,
                            uploadPartUrls: data.body.UploadPartUrls,
                            numChunks: numChunks
                        })
                      }
                  }
              })
              .catch((err) => {
                  this.setState( {status: null, alert: err.message});
              });  
    }

    async submitTask (urlResp) {
        //console.log(urlResp);
        var payload = {
            "TaskId": urlResp.taskId,
            "FileName": this.state.uploadFiles[0].name,
            "RequestBy": null,
            "Video": {
              "S3Object": {
                "Bucket": urlResp.uploadedS3Bucket,
                "Key": urlResp.uploadedS3KeyVideo,
              },
            },
            "PreProcessSetting": {
              "SampleMode": this.state.selectedVideoSampleMode,
              "SampleIntervalS": this.state.enableCustomInterval? this.state.inputVideoSampleIntervalS: this.state.selectedVideoSampleIntervalS,
              "SmartSample": this.state.enableSmartSample,
              "SimilarityThreshold": this.state.smartSampleThreshold,
            },
            "ExtractionSetting": {
                "Transcription": this.state.enableTranscription,
                "DetectLabel": this.state.enableDetectLabel,
                "DetectText": this.state.enableDetectText,
                "DetectCelebrity": this.state.enableDetectCelebrity,
                "DetectModeration": this.state.enableDetectModeration,
                "DetectLogo": this.state.enableDetectLogo,
                "ImageCaption": this.state.enableImageCaption,
                "DetectModerationConfidenceThreshold": this.state.rekDetectModerationThreshold,
                "DetectLabelConfidenceThreshold": this.state.rekDetectLabelThredhold,
                "DetectTextConfidenceThreshold": this.state.rekDetectTextThredhold,
                "DetectCelebrityConfidenceThreshold": this.state.rekDectectCelebrityThreshold,
                "AggregateResult": true,
            },
            "AnalysisSetting": {
                "ShotDetection": this.state.enableShotSceneDetection,
                "SceneDetection":this.state.enableShotSceneDetection,
                "ShotSimilarityThreshold": this.state.shotThreshold,
            },
            "EmbeddingSetting": {
                "Text": process.env.REACT_APP_VECTOR_SEARCH === "enable",
                "MultiModal": process.env.REACT_APP_VECTOR_SEARCH === "enable"
            }
          }
        //console.log(payload)

        this.setState({status: "loading"});
        const { username } = getCurrentUser().then((username) => {
            payload["RequestBy"] = username.username;
            // Start task
            FetchPost('/extraction/video/start-task', payload)
                .then((data) => {
                    this.setState({currentUploadingFileName: null})
                    var resp = data.body;
                    if (data.statusCode !== 200) {
                        //console.log(data.body);
                        this.setState( {status: null, alert: data.body});
                    }
                    else {
                        if (this.state.fileUploadedCounter == this.state.uploadFiles.length) {
                            this.resetState(null);
                            this.props.onSubmit();
                        }
                    }
                })
                .catch((err) => {
                    this.setState({currentUploadingFileName: null})
                    //console.log(err.message);
                    this.setState( {status: null, alert: err.message});
                });                      
            }
        )

    }

    async uploadFile(urlResp) {
        this.setState({status: "uploading"});
        let file = this.state.uploadFiles[0];
        if (urlResp.uploadPartUrls === null || urlResp.uploadPartUrls.length === 0) return;
            //console.log(this.state);
            // Upload each part to the corresponding pre-signed URL
            const uploadPromises = [];
            let parts = [];
            for (let i = 0; i < urlResp.numChunks; i++) {
              const startByte = i * (5 * 1024 * 1024);
              const endByte = Math.min(startByte + (5 * 1024 * 1024), file.size);
              const chunk = file.slice(startByte, endByte);
        
              const formData = new FormData();
              formData.append('file', chunk);
        
              let retries = 0;
              const uploadPromise = await fetch(urlResp.uploadPartUrls[i], {
                method: 'PUT',
                headers: {'Content-Type': ''},
                body: chunk,
              }).then((response) => {
                if (response.ok) {
                    //console.log(response.headers.get('Etag'));
                    parts.push({'ETag': response.headers.get('Etag'), 'PartNumber': i + 1})
                    this.setState({uploadedChunks: this.state.uploadedChunks + 1})
                    //console.log("uploaded", i, parts);
                    //console.log(this.state);
                }
              });
              uploadPromises.push(uploadPromise);
            };

            await Promise.all(uploadPromises).then(() => {
                    this.setState({fileUploadedCounter: this.state.fileUploadedCounter + 1});
                    //console.log("all completed");
                }
            ).then((response) => {
                // Call complete endpoint
                let payload = {
                    "TaskId": urlResp.taskId,
                    "FileName": file.name, 
                    "MultipartUpload": parts, 
                    "UploadId": urlResp.uploadId, 
                    "Action": "complete"
                };
                FetchPost("/extraction/video/manage-s3-presigned-url", payload)
                .then((result) => {
                    if (result.statusCode !== 200) {
                        this.setState( {alert: result.body});
                    }
                    else {
                        this.setState( {alert: null});
                        this.submitTask(urlResp);
                    }   
                })
                .catch((err) => {
                    this.setState( {alert: err.message});
                })
            });
    }

    handelFileChange = (e) => {
        const supportedFormats = ['avi', 'mov', 'mp4'];
        const filteredFiles = [];
        const invalidFiles= [];

        for (let i = 0; i < e.detail.value.length; i++) {
            const fileName = e.detail.value[i].name;
            const fileExtension = fileName.split('.').pop().toLowerCase();
    
            if (supportedFormats.includes(fileExtension)) {
                filteredFiles.push(e.detail.value[i]);
            } else {
                invalidFiles.push(fileName);
            }
        }
        this.setState({
            uploadFiles: filteredFiles,
            alert: invalidFiles.length === 0?null: `File(s) "${invalidFiles.join(', ')}" not in supported format (avi, mov, mp4) and has been removed.`
        });
    }

    getSelectedIntervalOption() {
        var option = this.llmParameters.video_sample_interval.find(item => item.value === this.state.selectedVideoSampleIntervalS);
        if (option !== null)
            return option;
        else 
            return {label: "", value: 1};
    }

    render() {
        return (
            <div className="videoupload">
                {this.state.alert !== null?
                <div><Alert statusIconAriaLabel="Warning" type="warning">{this.state.alert}</Alert><br/></div>
                :<div/>}
                <Wizard
                    i18nStrings={{
                        stepNumberLabel: stepNumber =>
                        `Step ${stepNumber}`,
                        collapsedStepsLabel: (stepNumber, stepsCount) =>
                        `Step ${stepNumber} of ${stepsCount}`,
                        skipToButtonLabel: (step, stepNumber) =>
                        `Skip to ${step.title}`,
                        navigationAriaLabel: "Steps",
                        cancelButton: "Cancel",
                        previousButton: "Previous",
                        nextButton: "Next",
                        submitButton: "Upload video and start analysis",
                        optional: "optional"
                    }}
                    onNavigate={this.handleNavigate}
                    onCancel={()=>{this.resetState();this.props.onCancel(null);}}
                    onSubmit={()=>this.handleSumbitTask()}
                    isLoadingNextStep={this.state.status !== null}
                    activeStepIndex={this.state.activeStepIndex}
                    steps={[
                        {
                            title: "Select a video file",
                            description:
                                "Upload a video file from your local disk. Supported format: .mp4, .mov, .avi",
                            content: (
                                <Container
                                    header={
                                        <Header variant="h2">
                                        Upload a video file
                                        </Header>
                                    }
                                >
                                <FileUpload
                                    onChange={this.handelFileChange}
                                    value={this.state.uploadFiles}
                                    i18nStrings={{
                                    uploadButtonText: e =>
                                        e ? "Choose files" : "Choose file",
                                    dropzoneText: e =>
                                        e
                                        ? "Drop files to upload"
                                        : "Drop file to upload",
                                    removeFileAriaLabel: e =>
                                        `Remove file ${e + 1}`,
                                    limitShowFewer: "Show fewer files",
                                    limitShowMore: "Show more files",
                                    errorIconAriaLabel: "Error"
                                    }}
                                    showFileLastModified
                                    showFileSize
                                    showFileThumbnail
                                    tokenLimit={3}
                                    multiple={false}
                                    constraintText="Supported video format: .mp4, .mov, .avi"
                                />
                                </Container>                                
                            )
                        },
                        {
                        title: "Extraction settings",
                        content: (
                            <SpaceBetween direction="vertical" size="l">
                                <Container header={
                                    <Header
                                    variant="h2"
                                    description="Video frame sampling and extraction"
                                    >
                                    Analyze the visual content
                                    </Header>
                                }>
                                    <ColumnLayout columns={1}>
                                        <FormField
                                            label="Select a sample interval"
                                            description="Number of frames sampled per second. For example, 2 means sample one frame every two seconds, 0.5 means sample 2 frames per second."
                                            >
                                            {this.llmParameters &&
                                            <Select disabled={this.state.enableCustomInterval}
                                                selectedOption={this.getSelectedIntervalOption()}
                                                onChange={({ detail }) => {
                                                    this.setState({selectedVideoSampleIntervalS: detail.selectedOption.value});
                                                }}
                                                options={this.llmParameters.video_sample_interval.map(item => ({
                                                    label: item.name, value: item.value
                                                }))}
                                                />}
                                        </FormField>
                                        
                                    </ColumnLayout>
                                    <ColumnLayout columns={2}>
                                        <Toggle checked={this.state.enableSmartSample} onChange={(e)=>
                                            {
                                                this.setState({enableSmartSample: e.detail.checked, enableShotSceneDetection: e.detail.checked});
                                            }}>
                                        Enable smart sampling (Amazon Bedrock Titan Multimodal Embedding and Vector DB)
                                        <div className='desc'>Reduce processing time and costs by removing similar images</div>
                                        </Toggle>
                                    </ColumnLayout>
                                    <br/>
                                    <hr/>
                                    <Box variant="h3">For each image frame</Box><br/>
                                    <ColumnLayout columns={2}>
                                        <Checkbox checked={this.state.enableDetectLabel} onChange={(e)=>this.setState({enableDetectLabel: e.detail.checked})}>
                                            Detect Label (Amazon Rekognition) 
                                        </Checkbox>
                                        <Checkbox checked={this.state.enableDetectModeration} onChange={(e)=>this.setState({enableDetectModeration: e.detail.checked})}>
                                            Detect Moderation (Amazon Rekognition)
                                        </Checkbox>
                                        <Checkbox checked={this.state.enableDetectText} onChange={(e)=>this.setState({enableDetectText: e.detail.checked})}>
                                            Detect Text (Amazon Rekognition)
                                        </Checkbox>
                                        <Checkbox checked={this.state.enableDetectCelebrity} onChange={(e)=>this.setState({enableDetectCelebrity: e.detail.checked})}>
                                            Detect Celebrity (Amazon Rekognition)
                                        </Checkbox>
                                        {/* <Checkbox checked={this.state.enableDetectLogo} onChange={(e)=>this.setState({enableDetectLogo: e.detail.checked})}>
                                            Detect Logo (Amazon Titan Anthropic Claude V3 Sonnet)
                                        </Checkbox> */}
                                        <Checkbox checked={this.state.enableImageCaption} onChange={(e)=>this.setState({enableImageCaption: e.detail.checked})}>
                                            Image summary (Amazon Bedrock Anthropic Claude V3 Haiku)
                                        </Checkbox>
                                    </ColumnLayout>
                                </Container>
                                <Container header={
                                    <Header
                                    variant="h2"
                                    >
                                    Analyze the audio content
                                    </Header>
                                }>
                                <Toggle checked={this.state.enableTranscription} onChange={(e)=>this.setState({enableTranscription: e.detail.checked})}>
                                    Transcribe audio (Amazon Transcribe)
                                    <div className='desc'>Generate audio transcriptions at the timestamp level (subtitles).</div>
                                </Toggle>
                                </Container>
                                <Container header={
                                        <Header variant="h2">Video Shot Analysis 
                                            <div className='shotwarn'>
                                                <Popover
                                                    header="Conceptual shots are grouped frames based on a threshold for a summary view, but may not reflect precise camera switches."
                                                    content="Adjust sampling frequency and thresholds for better accuracy, or use Amazon Rekognition's segment detection for precise results."
                                                >
                                                    <StatusIndicator type="info">
                                                    Limitation
                                                    </StatusIndicator>
                                                </Popover>
                                            </div>
                                        </Header>
                                    }>
                                        <ColumnLayout columns={1}>
                                            <Checkbox checked={this.state.enableShotSceneDetection} onChange={(e)=>this.setState({enableShotSceneDetection: e.detail.checked, enableSmartSample: true})}>
                                            Shot detection with summary (Amazon Bedrock Anthropic Claude V3 Haiku and Sonnet)
                                            <div className='desc'>
                                                Requires enabling Smart Sampling.
                                            </div>
                                            <div className='desc'>
                                                Shot detection group video frames to shots by utilizing the similarity score generated through Titan multimodal embeddings with vector database similarity comparison.
                                            </div>
                                            </Checkbox>
                                            <ExpandableSection defaultExpanded={false} headerText="Customize shot detection similiarity threshold">
                                            <FormField
                                                label=""
                                                description="Amazon Bedrock Titan multimodal embedding similarity score (FAISS L2) threshold: A new shot will be created when the similarity score between adjacent images exceeds this threshold."
                                                errorText={
                                                    !this.state.shotThresholdValid?"Please provide a decimal value greater than 0 and less than 2":""
                                                }
                                                >
                                                <div>
                                                    <input type="number" className="input"
                                                        value={this.state.shotThreshold} 
                                                        onChange={(e)=>{
                                                                this.setState({
                                                                    shotThreshold: e.target.value,
                                                                    shotThresholdValid: IsValidNumber(e.target.value) && e.target.value > 0 && e.target.value <= 2
                                                                })
                                                        }}
                                                    />
                                                </div>
                                            </FormField>
                                            </ExpandableSection>
                                        </ColumnLayout>
                                </Container>
                                <ExpandableSection variant="container" headerText="Advanced settings" defaultExpanded={this.state.advanceSettingExpand}>
                                    <ColumnLayout columns={2}>
                                        <FormField
                                            label="Customize sample interval"
                                            description="Customize the sampling interval if it is not available in the predefined list. For example, 2 means sample one frame every two seconds, 0.5 means sample 2 frames per second."
                                            errorText={
                                                this.state.enableCustomInterval && !this.state.inputVideoSampleIntervalSValid?"Please provide a decimal value greater than 0 and less than 10,000":""
                                            }
                                            >
                                            <Checkbox checked={this.state.enableCustomInterval} onChange={(e)=>this.setState({enableCustomInterval: e.detail.checked})}>
                                            </Checkbox>
                                            {this.state.enableCustomInterval &&
                                            <div>
                                                <input type="number" className="custom_interval"
                                                    value={this.state.inputVideoSampleIntervalS} 
                                                    onChange={(e)=>{
                                                            this.setState({
                                                                inputVideoSampleIntervalS: e.target.value,
                                                                inputVideoSampleIntervalSValid: IsValidNumber(e.target.value) && e.target.value > 0 && e.target.value <= 10000
                                                            })
                                                    }}
                                                />
                                            </div>}
                                        </FormField>
                                        <FormField
                                            label="Smart sampling threshold"
                                            description="Amazon Bedrock Titan multimodal embedding similarity score (FAISS L2) threshold: Images with scores below this threshold will be removed."
                                            errorText={!this.state.smartSampleThresholdValid ?"Please provide a decimal value between 0 and 2":""}
                                            stretch={true}
                                            >
                                                <Input value={this.state.smartSampleThreshold} onChange={
                                                    ({detail})=>{
                                                            this.setState({
                                                                smartSampleThreshold: detail.value,
                                                                smartSampleThresholdValid: IsValidNumber(detail.value) && detail.value >= 0 && detail.value <= 2
                                                            });
                                                    }                                                
                                                }></Input>
                                        </FormField>
                                    </ColumnLayout>
                                    <ColumnLayout columns={4}>
                                    <FormField
                                        label="Detect label threshold"
                                        description="Rekognition DetectLabel confidence score threshold"
                                        errorText={!this.state.rekDetectLabelThredholdValid?"Please provide a number between 0 and 100":null}
                                        stretch={true}
                                        >
                                            <Input value={this.state.rekDetectLabelThredhold} onChange={
                                                ({detail})=>{
                                                        this.setState({
                                                            rekDetectLabelThredhold: detail.value,
                                                            rekDetectLabelThredholdValid: IsValidNumber(detail.value) && detail.value >= 0 && detail.value <= 100
                                                        });
                                                }
                                            }></Input>
                                    </FormField>
                                    <FormField
                                        label="Detect moderation threshold"
                                        description="Rekognition DetectModeration confidence score threshold"
                                        errorText={!this.state.rekDetectModerationThresholdValid?"Please provide a number between 0 and 100":""}
                                        stretch={true}
                                        >
                                            <Input value={this.state.rekDetectModerationThreshold} onChange={({detail})=>
                                                {
                                                        this.setState({
                                                            rekDetectModerationThreshold: detail.value,
                                                            rekDetectModerationThresholdValid: IsValidNumber(detail.value) && detail.value >= 0 && detail.value <= 100
                                                        })
                                                }
                                            }></Input>
                                    </FormField>
                                    <FormField
                                        label="Detect text threshold"
                                        description="Rekognition DetectText confidence score threshold"
                                        errorText={!this.state.rekDetectTextThredholdValid?"Please provide a number between 0 and 100":""}
                                        stretch={true}
                                        >
                                            <Input value={this.state.rekDetectTextThredhold} onChange={({detail})=>
                                                {
                                                        this.setState({
                                                            rekDetectTextThredhold: detail.value,
                                                            rekDetectTextThredholdValid: IsValidNumber(detail.value) && detail.value >= 0 && detail.value <= 100
                                                        })
                                                }
                                            }></Input>
                                    </FormField>
                                    <FormField
                                        label="Detect celebrity threshold"
                                        description="Rekognition DetectCelebrity confidence score threshold"
                                        errorText={!this.state.rekDectectCelebrityThresholdValid?"Please provide a number between 0 and 100":null}
                                        stretch={true}
                                        >
                                            <Input value={this.state.rekDectectCelebrityThreshold} onChange={({detail})=>
                                                {
                                                        this.setState({
                                                            rekDectectCelebrityThreshold: detail.value,
                                                            rekDectectCelebrityThresholdValid: IsValidNumber(detail.value) && detail.value >= 0 && detail.value <= 100
                                                        })
                                                }
                                            }></Input>
                                    </FormField>                                    
                                    </ColumnLayout>
                                    
                                </ExpandableSection>
                            </SpaceBetween>
                        ),
                        },
                        {
                            title: "Upload vidoes and start analysis",
                            info: <Link variant="info">Info</Link>,
                            description:
                                "Confirm the videos below and start analysis",
                            content: (
                                <Container
                                    header={
                                        <Header variant="h2">
                                        Upload a video file
                                        </Header>
                                    }
                                >
                                    {this.state.uploadFiles.map((file,i)=>{
                                        return <div key={file + i.toString()} className='uploadedfile'>
                                            <div className='filename'>{file.name}</div>
                                            <div className='attribute'>{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                                            {this.state.currentUploadingFileName === file.name &&
                                                <div>
                                                    <ProgressBar
                                                        value={this.state.numChunks && this.state.uploadedChunks?(this.state.uploadedChunks/this.state.numChunks)*100:0}
                                                        status={this.state.numChunks && this.state.uploadedChunks && this.state.uploadedChunks === this.state.numChunks? "success":"in-progress"}
                                                        label="Uploading file"
                                                    />
                                                    <br/>
                                                </div>
                                            }                                        
                                        </div>
                                    })}

                                    
                                </Container>
                            )
                        },
                    ]}
                />

            </div>
        );
    }
}

export default VideoUpload;