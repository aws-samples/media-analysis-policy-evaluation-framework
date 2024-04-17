import React from 'react';
import './videoTrans.css'
import { DecimalToTimestamp } from "../resources/utility";
import { Button, Grid, Tabs, Alert, Spinner, ExpandableSection } from '@cloudscape-design/components';
import { FetchPost } from "../resources/data-provider";

class VideoTrans extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: "loading", // null, loading, loaded
            alert: null,
            uploadFile: [],

            item: null,

            showUploadModal: false,
            extractionSettingExpand: false,
            enableDetectText: true,
            enableDetectLabel: true,
            enableDetectModeration: true,
            enableDetectCelebrity: true,
            enableTranscription: true
        };
        this.item = null;
    }

    async componentDidMount() {
        if (this.state.item === null) {
          this.populateItem();    
        }
    }
    populateItem() {
        this.setState({status: "loading"});
        FetchPost("/extraction/video/get-task", {
          "TaskId": this.props.taskId,
          "DataTypes": ["Transcription"]
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

    handleSubtitleClick(timestamp) {
        //alert(timestamp);
        this.props.OnSubtitleClick(timestamp);
    }

    render() {
        return (
            <div className="videotrans">
                {this.state.item !== null && this.state.item !== undefined?
                <div>
                    <ExpandableSection headerText="Full transcription">
                    <div className="content">{this.state.item.Transcription.subtitles.map(i => i.transcription).join(' ')}</div>
                    </ExpandableSection>

                    <div className='title'>Language code </div>
                    <div className="content">{this.state.item.Transcription.language_code}</div>
                    <br/>
                    <div className='title'>Subtitles</div>
                   {this.state.item.Transcription.subtitles.map((l,i)=>{
                            return  <div key={`subtitle_${l.start_ts}`} className='subtitle' onClick={() => {this.handleSubtitleClick(l.start_ts)}}>
                                <div className="time">{DecimalToTimestamp(l.start_ts)}</div>
                                <div className="trans">{l.transcription}</div>
                            </div>
                        })}
                </div>
                : <Spinner/>
                }
            </div>
        );
    }
}

export default VideoTrans;