import React from 'react';
import './videoInsight.css'
import { FetchData } from "../resources/data-provider";
import { Button, Grid, Tabs, Alert, Popover } from '@cloudscape-design/components';
import ProgressBar from './progressBar';

class VideoInsight extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: "loading", // null, loading, loaded
            alert: null,

            selectedLogo: null,
            selectedLabel: null,
            selectedLabelCategory: null,
            selectedText: null,
            selectedModeration: null,
            selectedCelebrity: null
        };
        this.item = null;
    }

    async componentDidMount() {
        // Call the API to fetch data
        if (this.props.item) {
          this.setState(
            {
                selectedLogo: this.props.item.DetectLogoAgg && this.props.item.DetectLogoAgg.length > 0 && this.constructItem(this.props.item.DetectLogoAgg[0]),
                selectedLabelCategory: this.props.item.DetectLabelCategoryAgg && this.props.item.DetectLabelCategoryAgg.length > 0 && this.constructItem(this.props.item.DetectLabelCategoryAgg[0]),
                selectedLabel: this.props.item.DetectLabelAgg && this.props.item.DetectLabelAgg.length > 0 && this.constructItem(this.props.item.DetectLabelAgg[0]),
                selectedText: this.props.item.DetectTextAgg && this.props.item.DetectTextAgg.length > 0 && this.constructItem(this.props.item.DetectTextAgg[0]),
                selectedModeration: this.props.item.DetectModerationAgg && this.props.item.DetectModerationAgg.length > 0 && this.constructItem(this.props.item.DetectModerationAgg[0]),
                selectedCelebrity: this.props.item.DetectCelebrityAgg && this.props.item.DetectCelebrityAgg.length > 0 && this.constructItem(this.props.item.DetectCelebrityAgg[0]),
            }
          )
        }
    }

    handleProgressBarClick = e=> {
        this.props.OnProgressBarClick(e);
    }

    constructItem = (l) => {
        let ts = [];
        l.timestamps.forEach(t => {
            ts.push({timestamp: t, lable: l.name});
        })
        return {
            name: l.name,
            timestamps: ts
        };
    }

    render() {
        return (
            <div className="videoinsight">
                {this.state.alert !== null && this.state.alert.length > 0?
                <Alert statusIconAriaLabel="Warning" type="warning">
                {this.state.alert}
                </Alert>:<div/>}
                
                {this.props.item !== null?
                <div>
                    {this.props.item.DetectCelebrityAgg !== undefined && this.props.item.DetectCelebrityAgg.length > 0?
                    <div className='section'>
                        <div className="title">Celebrities</div>
                        {this.props.item.DetectCelebrityAgg.map((l,i)=>{
                            return  <div key={"logo_" +l.name} className={this.state.selectedCelebrity !== null && this.state.selectedCelebrity.name == l.name?"celebrity-selected":"celebrity"} onClick={() => {
                                let ls = this.constructItem(l);
                                this.setState({selectedCelebrity: ls});
                            }}>{l.name}</div>
                        })}
                        <div className='progressbar'>
                        <ProgressBar labelType="celebrity"
                            duration={this.props.item.MetaData.VideoMetaData.Duration} 
                            labels={this.state.selectedCelebrity !== null && this.state.selectedCelebrity.timestamps !== null?this.state.selectedCelebrity.timestamps:[]} 
                            OnLabelClick={this.handleProgressBarClick}
                        />
                        </div>
                    </div>
                    :<div/>}
                    {this.props.item.DetectLogoAgg !== undefined && this.props.item.DetectLogoAgg.length > 0?
                    <div className='section'>
                        <div className="title">Brand and logos</div>
                        {this.props.item.DetectLogoAgg.map((l,i)=>{
                            return  <div key={"logo_" +l.name} className={this.state.selectedLogo !== null && this.state.selectedLogo.name == l.name?"logo-selected":"logo"} onClick={() => {
                                this.setState({selectedLogo: this.constructItem(l)});
                            }}>{l.name}</div>
                        })}
                        <div className='progressbar'>
                        <ProgressBar labelType="logo"
                            duration={this.props.item.MetaData.VideoMetaData.Duration} 
                            labels={this.state.selectedLogo !== null && this.state.selectedLogo.timestamps !== null?this.state.selectedLogo.timestamps:[]} 
                            OnLabelClick={this.handleProgressBarClick}
                        />
                        </div>
                    </div>
                    :<div/>}
                    {this.props.item.DetectLabelCategoryAgg !== undefined && this.props.item.DetectLabelCategoryAgg.length > 0?
                    <div className='section'>
                        <div className="title">Label category</div>
                        {this.props.item.DetectLabelCategoryAgg.map((l,i)=>{
                            return  <div key={"logo_" +l.name} className={this.state.selectedLabelCategory !== null && this.state.selectedLabelCategory.name == l.name?"label-selected":"label"} onClick={() => {
                                let ls = this.constructItem(l);
                                this.setState({selectedLabelCategory: ls});
                            }}>{l.name}</div>
                        })}
                        <div className='progressbar'>
                        <ProgressBar labelType="label"
                            duration={this.props.item.MetaData.VideoMetaData.Duration} 
                            labels={this.state.selectedLabelCategory !== null && this.state.selectedLabelCategory.timestamps !== null?this.state.selectedLabelCategory.timestamps:[]} 
                            OnLabelClick={this.handleProgressBarClick}
                        />
                        </div>
                    </div>
                    :<div/>}
                    {this.props.item.DetectLabelAgg !== undefined && this.props.item.DetectLabelAgg.length > 0?
                    <div className='section'>
                        <div className="title">Label</div>
                        {this.props.item.DetectLabelAgg.map((l,i)=>{
                            return  <div key={"logo_" +l.name} className={this.state.selectedLabel !== null && this.state.selectedLabel.name == l.name?"label-selected":"label"} onClick={() => {
                                let ls = this.constructItem(l);
                                this.setState({selectedLabel: ls});
                            }}>{l.name}</div>
                        })}
                        <div className='progressbar'>
                        <ProgressBar labelType="label"
                            duration={this.props.item.MetaData.VideoMetaData.Duration} 
                            labels={this.state.selectedLabel !== null && this.state.selectedLabel.timestamps !== null?this.state.selectedLabel.timestamps:[]} 
                            OnLabelClick={this.handleProgressBarClick}
                        />
                        </div>
                    </div>
                    :<div/>}
                    {this.props.item.DetectModerationAgg !== undefined && this.props.item.DetectModerationAgg.length > 0?
                    <div className='section'>
                        <div className="title">Moderation labels</div>
                        {this.props.item.DetectModerationAgg.map((l,i)=>{
                            return  <div key={"logo_" +l.name} className={this.state.selectedModeration !== null && this.state.selectedModeration.name == l.name?"moderation-selected":"moderation"} onClick={() => {
                                let ls = this.constructItem(l);
                                this.setState({selectedModeration: ls});
                            }}>{l.name}</div>
                        })}
                        <div className='progressbar'>
                        <ProgressBar labelType="moderation"
                            duration={this.props.item.MetaData.VideoMetaData.Duration} 
                            labels={this.state.selectedModeration !== null && this.state.selectedModeration.timestamps !== null?this.state.selectedModeration.timestamps:[]} 
                            OnLabelClick={this.handleProgressBarClick}
                        />
                        </div>
                    </div>
                    :<div/>}
                    {this.props.item.DetectTextAgg !== undefined && this.props.item.DetectTextAgg.length > 0?
                    <div className='section'>
                        <div className="title">Text</div>
                        {this.props.item.DetectTextAgg.map((l,i)=>{
                            return  <div key={"logo_" +l.name} className={this.state.selectedText !== null && this.state.selectedText.name == l.name?"text-selected":"text"} onClick={() => {
                                let ls = this.constructItem(l);
                                this.setState({selectedText: ls});
                            }}>{l.name}</div>
                        })}
                        <div className='progressbar'>
                        <ProgressBar labelType="text"
                            duration={this.props.item.MetaData.VideoMetaData.Duration} 
                            labels={this.state.selectedText !== null && this.state.selectedText.timestamps !== null?this.state.selectedText.timestamps:[]} 
                            OnLabelClick={this.handleProgressBarClick}
                        />
                        </div>
                    </div>
                    :<div/>}
                </div>
                :<div/>
                }
            </div>
        );
    }
}

export default VideoInsight;