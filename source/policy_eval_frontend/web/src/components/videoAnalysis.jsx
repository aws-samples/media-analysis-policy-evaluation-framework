import React from 'react';
import './videoAnalysis.css'
import { FetchPost } from "../resources/data-provider";
import { Button, Box, SpaceBetween, ButtonDropdown, Modal, Select, Spinner, Pagination, Toggle, Icon } from '@cloudscape-design/components';
import { getCurrentUser } from 'aws-amplify/auth';

class VideoAnalysis extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: null, // null, loading, loaded
            alert: null,
            llmPromptsExpand: false,
            item: null,

            showEvalModal: false,
            showPreview: false,
            showDeleteConfirmModal: false,

            selectedEvalTemplate: null,
            promptsTemplateBackup: null,
            promptsTemplate: null,
            selectedBedrockModel: null,
            evaluationResult: null,
            selectedTaskId: null,

            pageSize: 10,
            currentPageIndex: 1,
            totalItems: 0,
            items: null
        };
        this.item = null;
        this.llmParameters = null;
        this.textareaRef = React.createRef();
        this.evaluationResultRef = React.createRef();
    }

    async componentDidMount() {
        // Call the API to fetch data
        if (this.props.item !== undefined && this.props.item !== null && this.props.item.evaluationResult !== undefined && this.state.selectedEvalTemplate === null) {
          this.setState({selectedEvalTemplate: this.props.item.evaluationResult.prompts})   
        }
        if (this.llmParameters === null) {
            fetch('./llm-eval-template.json')
            .then(response => response.json())
            .then(data => {
                this.llmParameters = data;
                this.setState({selectedBedrockModel: data.bedrock_model_ids[0]});
            })
            .catch(error => {
                console.error('Error fetching llm template:', error);
            });
        }
        if (this.state.item === null)
            this.populateItem();
        if (this.state.items === null)
            this.populateTasks();
    }
    populateItem() {
        this.setState({status: "loading"});
        FetchPost("/extraction/video/get-task", {
          "TaskId": this.props.taskId,
          "DataTypes": ["Transcription", "ImageCaption","DetectLabel", "DetectText", "DetectModeration", "DetectCelebrity", "DetectLogo"],
          "PageSize": 30
        }).then((data) => {
                var resp = data.body;
                if (data.statusCode !== 200) {
                    this.setState( {status: null, alert: data.body});
                }
                else {
                    if (resp !== null) {
                        this.setState(
                            {
                                item: resp,
                                status: null,
                                alert: null,
                            }
                        );
                    }
                }
            })
            .catch((err) => {
                this.setState( {status: null, alert: err.message});
            });  
    }
    populateTasks(fromIndex=null) {
        this.setState({status: "loading"});
        if (fromIndex === null)
            fromIndex = this.state.currentPageIndex
        
          FetchPost("/evaluation/get-tasks", {
              "PageSize": this.state.pageSize,
              "FromIndex": (fromIndex - 1) * this.state.pageSize,
              "VideoTaskId": this.props.taskId,
          },"EvaluationService").then((data) => {
                  var resp = data.body;
                  if (data.statusCode !== 200) {
                      this.setState( {status: null, alert: data.body});
                  }
                  else {
                      if (resp !== null) {
                          //console.log(items);
                          this.setState(
                              {
                                  items: resp.Tasks,
                                  totalItems: resp.Total,
                                  status: null,
                                  alert: null,
                              }
                          );
                      }
                  }
              })
              .catch((err) => {
                  this.setState( {status: null, alert: err.message});
              });              
    }

    formatDetectItem(array, itemName) {
        let result = "";
        array.forEach(item => {
            result += `${itemName} "${item.name}" detected in the video at timestamp ${item.timestamps.join(",")}.\n`;
        });
        return result.trim();
    }

    formatPrompts(prompts) {
        let trans = null;
        if ((this.state.item.Transcription !== undefined && this.state.item.Transcription!== null)  && (this.state.item.Transcription.subtitles !== undefined && this.state.item.Transcription.subtitles !== null)) 
            trans = this.state.item.Transcription.subtitles.map(item => item.transcription).join(' ');

        let p = prompts.replace("##TRANSCRIPTION##", trans === null? "": trans);
        if (this.state.item ) {
            p = p.replace("##SUBTITLE##", this.state.item.Transcription?JSON.stringify(this.state.item.Transcription.subtitles):"");
            p = p.replace("##LABEL##", this.state.item.DetectLabel?JSON.stringify(this.state.item.DetectLabel.Items, "Label"):"");
            p = p.replace("##LOGO##", this.state.item.DetectLogo?JSON.stringify(this.state.item.DetectLogo.Items, "Logo"):"");
            p = p.replace("##TEXT##", this.state.item.DetectText?JSON.stringify(this.state.item.DetectText.Items, "Text"):"");
            p = p.replace("##CELEBRITY##", this.state.item.DetectCelebrity?JSON.stringify(this.state.item.DetectCelebrity.Items, "Celebrity"):"");
            p = p.replace("##MODERATION##", this.state.item.DetectModeration?JSON.stringify(this.state.item.DetectModeration.Items, "Moderation"):"");
            p = p.replace("##IMAGECAPTION##", this.state.item.ImageCaption?JSON.stringify(this.state.item.ImageCaption.Items, "Moderation"):"");
        }
        return p;
    }
    handleDryRun = (e) => {
        this.setState({status: "loading", evaluationResult: null});
        var payload = {
            "Prompts": this.formatPrompts(this.state.promptsTemplate),
            "LLMsModelId": this.state.selectedBedrockModel === null?null: this.state.selectedBedrockModel.value
          };
        FetchPost('/evaluation/invoke-llm', payload, "EvaluationService")
        .then((data) => {
            var resp = data.body;
            if (data.statusCode !== 200) {
                //console.log(data.body);
                this.setState( {status: null, alert: data.body});
            }
            else {
                if (resp !== null) {
                    this.setState(
                        {
                            status: null,
                            alert: null,
                        }
                    );
                    this.setState({evaluationResult : resp.response});
                    this.evaluationResultRef.current.focus();
                }
            }
        })
        .catch((err) => {
            //console.log(err.message);
            this.setState( {status: null, alert: err.message});
        });  
    }

    handleEvaluation = (e) => {
        this.setState({status: "loading", evaluationResult: null});
        const { username } = getCurrentUser().then((username) => {
            var payload = {
                "VideoTaskId":this.props.taskId,
                "Prompts": this.formatPrompts(this.state.promptsTemplate),
                "LlmModelId": this.state.selectedBedrockModel === null?null: this.state.selectedBedrockModel.value,
                "LlmSource": "bedrock",
                "Name": this.state.selectedEvalTemplate !== null?this.state.selectedEvalTemplate.label:"",
                "RequestBy": username.username
          };
            FetchPost('/evaluation/create-task', payload, "EvaluationService")
            .then((data) => {
                var resp = data.body;
                if (data.statusCode !== 200) {
                    //console.log(data.body);
                    this.setState( {status: null, alert: data.body});
                }
                else {
                    if (resp !== null) {
                        console.log(resp);
                        this.setState(
                            {
                                status: null,
                                alert: null,
                                items: null,
                                showEvalModal: false
                            }
                        );
                        this.populateTasks();
                    }
                }
            })
            .catch((err) => {
                //console.log(err.message);
                this.setState( {status: null, alert: err.message});
            });  
        })
    }

    handleDelete = (e) => {
        this.setState({status: "loading"});
            var payload = {
                "Id":this.state.selectedTaskId
          };
            FetchPost('/evaluation/delete-task', payload, "EvaluationService")
            .then((data) => {
                var resp = data.body;
                if (data.statusCode !== 200) {
                    //console.log(data.body);
                    this.setState( {status: null, alert: data.body});
                }
                else {
                    if (resp !== null) {
                        console.log(resp);
                        this.setState(
                            {
                                status: null,
                                alert: null,
                                items: this.state.items.filter(item => item.Id !== this.state.selectedTaskId),
                                showDeleteConfirmModal: false
                            }
                        );
                        this.populateTasks();
                    }
                }
            })
            .catch((err) => {
                //console.log(err.message);
                this.setState( {status: null, alert: err.message});
            });  
    }

    render() {
        return (
            <div className="videoeval">
                <div className='action'>
                    <Button onClick={()=>{this.populateTasks();}}>
                        <Icon name="refresh" />
                    </Button>
                    <Button onClick={()=>{this.setState({showEvalModal: true, evaluationResult: null, promptsTemplate: "", selectedEvalTemplate: null})}}>Analyze Video</Button>
                </div>
                <div className='pager'>
                <Pagination
                    currentPageIndex={this.state.currentPageIndex}
                    onChange={({ detail }) => {
                            this.setState({currentPageIndex: detail.currentPageIndex, items:null});
                            this.populateTasks(detail.currentPageIndex);
                        }
                    }
                    pagesCount={parseInt(this.state.totalItems/this.state.pageSize)+1}
                    disabled={this.state.items === undefined || this.state.items === null || this.state.items.length === 0}
                    />
                </div>
                {this.state.status === "loading"?<Spinner/>:<div/>}
                <div className='tasks'>
                {this.state.items !== undefined && this.state.items !== null?this.state.items.map((l,i)=>{
                    return <div className='task'>
                        <div className='delete' onClick={()=>{this.setState({showDeleteConfirmModal: true, selectedTaskId: l.Id})}}><Icon name="remove" onClick={()=>{this.setState({showDeleteConfirmModal: true, selectedTaskId: l.Id})}} /></div>
                        <div className='title'>{l.Name !== undefined? l.Name: ""}</div>
                        <div className='ts'>{new Date(l.RequestTs).toLocaleString()} </div>
                        <div className='status'>{l.Status !== undefined? l.Status: ""}</div>
                        <div className={l.Status === "completed"?"prompt":"prompt_disabled"} onClick={()=> {
                            if (l.Status === "completed") {
                                this.setState({
                                showEvalModal: true, 
                                evaluationResult: l.Result, 
                                promptsTemplate: l.Prompts,
                                selectedEvalTemplate: l.Name? {label: l.Name}: null
                            })
                        }}}>{l.Prompts.substring(0,100)} {l.Prompts.length > 100? "...":""}</div>
                   </div>
                }):<div/>}
                </div>
                <Modal
                    onDismiss={() => this.setState({showDeleteConfirmModal: false})}
                    visible={this.state.showDeleteConfirmModal}
                    header="Delete the task"
                    size='medium'
                    footer={
                        <Box float="right">
                          <SpaceBetween direction="horizontal" size="xs">
                            <Button variant="link" onClick={() => this.setState({showDeleteConfirmModal: false})}>Cancel</Button>
                            <Button variant="primary" loading={this.state.status === "loading"} onClick={this.handleDelete}>Yes</Button>
                          </SpaceBetween>
                        </Box>
                      }
                >
                    Are you sure you want to delete the analysis task?
                </Modal>
                <Modal 
                    visible={this.state.showEvalModal} 
                    size="max" 
                    onDismiss={()=>{this.setState({showEvalModal:false})}}
                    header={"Analyze video with Generative AI"}
                    footer={
                        <div>
                        <div className='modalfooterleft'>
                            <Button variant='primary' 
                                onClick={this.handleDryRun} 
                                disabled={this.state.promptsTemplate === null || this.state.promptsTemplate.length === 0}
                                loading={this.state.status === "loading"}>
                            Dry Run</Button>
                            &nbsp;
                            <Button onClick={()=>{this.setState({evaluationResult:null, selectedEvalTemplate: null, promptsTemplate: null, promptsTemplateBackup: null})}}>Clear</Button>
                        </div>
                        <div className='modalfooterright'>
                            <Button variant='primary' 
                                onClick={this.handleEvaluation} 
                                disabled={this.state.promptsTemplate === null || this.state.promptsTemplate.length === 0 || this.state.status === "loading"}
                            >
                            Run & Save</Button>
                            &nbsp;
                            <Button onClick={()=>{this.setState({showEvalModal: false})}}>Cancel</Button>
                        </div>
                        </div>
                    }
                >
                    <div className='videoanalysis'>
                    <div className='selectmodel'>
                        <div className='key'>Select a Bedrock LLMs model</div>
                        {this.llmParameters !== null?
                        <Select 
                            selectedOption={this.state.selectedBedrockModel}
                            onChange={({ detail }) => {
                                this.setState({selectedBedrockModel: detail.selectedOption})
                            }}
                            options={this.llmParameters.bedrock_model_ids.map(item => ({
                                label: item.name, value: item.value
                            }))}
                            />:<div/>}
                    </div>
                    <div className='selecttemp'>
                        <div className='key'>Use a sample template</div>
                        <div className='desc'>Get started quickly with predefined prompts templates. Or, type your own prompts directly without using a template.</div>
                        {this.llmParameters !== null?
                        <Select
                            selectedOption={this.state.selectedEvalTemplate}
                            onChange={({ detail }) =>
                                {
                                    //console.log(detail.selectedOption.temp);
                                    this.setState({
                                        selectedEvalTemplate: detail.selectedOption,
                                        promptsTemplate: detail.selectedOption.temp,
                                        promptsTemplateBackup: detail.selectedOption.temp,
                                        selectedBedrockModel: {label:detail.selectedOption.modelId, value: detail.selectedOption.modelId},
                                        evaluationResult: null,
                                        showPreview: false
                                    })
                                }
                            }
                            options={this.llmParameters.templates.map(item => ({
                                label: item.name,
                                //value: item.id,
                                temp: item.prompts_template,
                                modelId: item.bedrock_llm_model_id,
                                kbId: item.bedrock_knowledge_base_id
                            }))}
                            />:<div/>}
                    </div>
                    <div className='promptseditor'>
                        <div className='key'>Edit the prompts template</div>
                        <div className='desc'>A prompt instructs the LLM model on how to complete a task. Click the "Placeholder" button to add video metadata placeholders to the prompt.</div>
                        <textarea className='editor' rows={20} cols={40}
                            onChange={(e) => {
                                this.setState({promptsTemplate: e.target.value, promptsTemplateBackup: e.target.value});
                            }
                            }
                            value={this.state.promptsTemplate}
                            disableBrowserAutocorrect
                            placeholder="LLMs prompts template with placeholders"
                            ref={this.textareaRef}
                            />
                        <div className='selectplaceholder'>
                            <ButtonDropdown
                                items={[
                                    { text: "Transcription ##TRANSCRIPTION##", id: "##TRANSCRIPTION##" },
                                    { text: "Subtitle ##SUBTITLE##", id: "##SUBTITLE##" },
                                    { text: "DetectLabel ##LABEL##", id: "##LABEL##" },
                                    { text: "DetectText ##TEXT##", id: "##TEXT##" },
                                    { text: "DetectCelebrity ##CELEBRITY##", id: "##CELEBRITY##" },
                                    { text: "DetectModeration ##MODERATION##", id: "##MODERATION##" },
                                    // { text: "DetectLogo ##LOGO##", id: "##LOGO##" },
                                    { text: "Image caption ##IMAGECAPTION##", id: "##IMAGECAPTION##" },
                                ]}
                                onItemClick={(e) => {
                                    const prompts = this.state.promptsTemplate === null? "": this.state.promptsTemplate;
                                    const textarea = this.textareaRef.current;
                                    const { selectionStart, selectionEnd } = textarea;
                                    const textBeforeCursor = prompts.slice(0, selectionStart);
                                    const textAfterCursor = prompts.slice(selectionEnd);
                                    const newText = `${textBeforeCursor}${e.detail.id}${textAfterCursor}`;
                                    this.setState({ promptsTemplate: newText, promptsTemplateBackup: newText });
                                    // Move cursor after the inserted placeholder
                                    textarea.selectionStart = textarea.selectionEnd = selectionStart + e.detail.id.length;
                                    textarea.focus();
                                }
                                }
                                >
                                Add metadata placeholder
                            </ButtonDropdown>
                        </div>
                        <div className='previewtoggle'>
                            <Toggle
                                disabled={this.state.promptsTemplate === null || this.state.promptsTemplate.length === 0}
                                onChange={({ detail }) =>
                                    {
                                        let prompts = this.state.promptsTemplateBackup;
                                        if (detail.checked) {
                                            prompts = this.formatPrompts(this.state.promptsTemplate);
                                        }
                                        this.setState({
                                            showPreview: detail.checked,
                                            promptsTemplate: prompts
                                        });
                                    }
                                }
                                checked={this.state.showPreview}
                                >
                                Preview (replace placeholders with video metadata)
                            </Toggle>
                        </div>
                    </div>
                    <div className='llmresp'>
                        <div className='key'>LLMs response</div>
                        {this.state.evaluationResult !== null?
                        <div className='llm-resp' ref={this.evaluationResultRef}>{this.state.evaluationResult}</div>:<div/>}
                    </div>
                    </div>
                </Modal>
            </div>
        );
    }
}

export default VideoAnalysis;