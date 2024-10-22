import React from 'react';
import './videoSearch.css'
import { Button, TextFilter, Cards, Alert, Spinner, Icon, Modal, Box, SpaceBetween, Badge, ButtonDropdown, ExpandableSection } from '@cloudscape-design/components';
import { FetchPost } from "../resources/data-provider";
import DefaultThumbnail from '../static/default_thumbnail.png';
import Slider from '@mui/material/Slider';
import { getCurrentUser } from 'aws-amplify/auth';
import sample_images from '../resources/sample-images.json'
import {ReactComponent  as PlayButton} from '../static/play-button.svg'

class VideoSearch extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: "loading", // null, loading, loaded
            alert: null,
            filterText: null,
            uploadFile: [],
            items: [],
            selectedItemId: null,
            pageSize: 8,
            mmScoreThreshold: 1.52,
            textScoreThreshold: 1.003,

            selectedSearchOptionId: process.env.REACT_APP_VECTOR_SEARCH === "enable"?"text":"video_name",
            imageBytes: null,

            showDeleteConfirmModal: false,
            showFrame: [],
            showSampleImages: false,

            textScoreExpanded: false,
            imageScoreExpanded: false
        };

        this.showMoreNumber = 8;
        this.searchTimer = null;
        this.searchOptions = process.env.REACT_APP_VECTOR_SEARCH === "enable"?
            [
                { text: "Keyword search", id: "text" },
                { text: "Semantic search", id: "text_embedding" },
                { text: "Multimodal search", id: "mm_embedding"},
            ]: 
            [{ text: "Video name", id: "video_name" }];
    }

    handleVideoClick = (taskId, autoPlay) => {
        //console.log(autoPlay);
        this.props.onThumbnailClick(taskId, autoPlay);
    }

    async componentDidMount() {
        if (this.state.items === null || this.state.items.length === 0)  {
          this.populateItems();    
        }
    }

    componentDidUpdate(prevProps) {
        if (prevProps.refreshSearchTaskId !== this.props.refreshSearchTaskId) {
            this.populateItems();    
        }
      }

    populateItems() {
          this.setState({status: "loading"});
          const { username } = getCurrentUser().then((username)=>{
            FetchPost(this.state.selectedSearchOptionId === "video_name"?"/extraction/video/search-task":"/extraction/video/search-task-vector", {
                "SearchText": this.state.filterText,
                "Source": this.state.selectedSearchOptionId,
                "ImageBytes": this.state.imageBytes === null? null: this.state.imageBytes.split("base64,")[1],
                "RequestBy": username.username,
                "PageSize": this.state.pageSize,
                "FromIndex": 0,
                "ScoreThreshold": this.state.selectedSearchOptionId === "text_embedding"? this.state.textScoreThreshold: this.state.mmScoreThreshold
            }).then((data) => {
                    var resp = data.body;
                    if (data.statusCode !== 200) {
                        this.setState( {status: null, alert: data.body});
                    }
                    else {
                        if (resp !== null) {
                            var items = resp;
                            //console.log(items);
                            this.setState(
                                {
                                    items: items === null?[]:items,
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

          )

      }

      handleDelete = e => {
        if (this.state.selectedItemId === null) return;

        this.setState({status: "loading"});
        FetchPost("/extraction/video/delete-task", {
            "TaskId": this.state.selectedItemId
          }).then((data) => {
                  var resp = data.body;
                  if (data.statusCode !== 200) {
                      this.setState( {status: null, alert: data.body, showDeleteConfirmModal: false});
                  }
                  else {
                      if (resp !== null) {
                          //console.log(resp);
                          this.setState(
                              {
                                  status: null,
                                  alert: null,
                                  items: this.state.items.filter(item => item.TaskId !== this.state.selectedItemId),
                                  selectedItemId: null,
                                  showDeleteConfirmModal: false
                              }
                          );
                      }
                  }
              })
              .catch((err) => {
                  this.setState( {status: null, alert: err.message, showDeleteConfirmModal: false});
              });  
      }
  
    handleSearchChange = (e) => {
        this.setState({filterText: e.detail.filteringText});
        /*clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => {
          this.populateItems();
        }, 1000); */
    }

    handleImageChange = (event) => {
        const file = event.target.files[0];
    
        if (file) {
          const reader = new FileReader();
    
          //const base64Str = reader.result;
          reader.onloadend = () => {
            this.setState({
              imageBytes: reader.result,
            });
          };
    
          reader.readAsDataURL(file);
        }
      };

    displaySearchOptionText() {
        var item = this.searchOptions.find(item => item.id === this.state.selectedSearchOptionId);
        if (item !== null) return item.text;
        else return "";
    }

    handelClear = (e) => {
        this.setState({
            selectedSearchOptionId: process.env.REACT_APP_VECTOR_SEARCH === "enable"?"text":"video_name",
            filterText: null,
            imageBytes: null,
        });
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => {
            this.populateItems();
        }, 500); 
    }

    handleSampleSelect = e => {
        this.setState({
            showSampleImages: false,
            imageBytes: e.detail.selectedItems[0].image_bytes,
            status: null});

    }

    render() {
        return (
            <div className="videosearch">
                {this.state.alert !== undefined && this.state.alert !== null && this.state.alert.length > 0?
                <Alert statusIconAriaLabel="Warning" type="warning">
                {this.state.alert}
                </Alert>:<div/>}
                     <div className='searchinput'>
                        <div className="input-source">
                        <ButtonDropdown variant='primary'
                            items={this.searchOptions}
                            onItemClick={(e) => {
                                console.log(e);
                                this.setState({selectedSearchOptionId: e.detail.id});
                            }}
                            >
                            {this.displaySearchOptionText()}
                        </ButtonDropdown>
                        </div>
                        <div className="input-text">
                        <TextFilter
                            filteringText={this.state.filterText}
                            filteringPlaceholder="Search"
                            filteringAriaLabel="Search video"
                            onChange={this.handleSearchChange}
                        />
                        </div>
                        <div className='search'>
                            <Button variant='primary' onClick={()=>{this.populateItems();}}>
                                <Icon name="search" />&nbsp;&nbsp;Search
                            </Button>&nbsp;
                            <Button onClick={this.handelClear}>
                            <svg className="clear-icon" fill="#0062ff" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="9723" >
                                <g id="SVGRepo_bgCarrier" stroke-width="0"/>
                                <g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"/>
                                <g id="SVGRepo_iconCarrier">
                                <defs>
                                <style type="text/css"/>
                                </defs>
                                <path d="M899.1 869.6l-53-305.6H864c14.4 0 26-11.6 26-26V346c0-14.4-11.6-26-26-26H618V138c0-14.4-11.6-26-26-26H432c-14.4 0-26 11.6-26 26v182H160c-14.4 0-26 11.6-26 26v192c0 14.4 11.6 26 26 26h17.9l-53 305.6c-0.3 1.5-0.4 3-0.4 4.4 0 14.4 11.6 26 26 26h723c1.5 0 3-0.1 4.4-0.4 14.2-2.4 23.7-15.9 21.2-30zM204 390h272V182h72v208h272v104H204V390z m468 440V674c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v156H416V674c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v156H202.8l45.1-260H776l45.1 260H672z" p-id="9724"/>
                                </g>
                            </svg>&nbsp;&nbsp;Clear
                            </Button>&nbsp;
                            <Button onClick={()=>{this.populateItems();}}>
                                <Icon name="refresh" />
                            </Button>
                        </div>
                        {this.state.selectedSearchOptionId == "mm_embedding"?
                        <div className="search-by-image">
                            <div className='title'>Perform a search using multimodal embedding</div>
                            {this.props.readonlyMode?
                                <div className='mm_sample'>
                                    <Button onClick={()=>{this.setState({showSampleImages: true})}}>Choose a sample image</Button>
                                    <Modal
                                        onDismiss={()=>{this.setState({showSampleImages: false})}}
                                        visible={this.state.showSampleImages}
                                        header="Choose a sample image for searching"
                                        size="large"
                                        >
                                        <div>
                                            <Cards
                                                onSelectionChange={this.handleSampleSelect}
                                                selectedItems={[]}
                                                selectionType="single"
                                                ariaLabels={{
                                                    itemSelectionLabel: (e, n) => `select ${n.id}`,
                                                    selectionGroupLabel: "Image selection"
                                                }}
                                                cardDefinition={{
                                                    header: item => (
                                                        <img src={item.image_bytes} alt={item.name} width="100%"></img>
                                                    ),
                                                    sections: [
                                                    {
                                                        id: "description",
                                                        content: e => e.name
                                                    }
                                                    ]
                                                }}
                                                cardsPerRow={[
                                                    { cards: 1 },
                                                    { minWidth: 500, cards: 2 }
                                                ]}
                                                items={sample_images}                                    
                                                />
                                        </div>
                                    </Modal>
                                </div>:
                                <div>
                                    <div className='desc'>Upload an image</div>
                                    <input className='input' type="file" accept="image/*" onChange={this.handleImageChange} />
                                </div>
                            }
                            
                            {this.state.imageBytes !== null?
                                <div className='image-container'>
                                    <img className="uploaded-image" src={this.state.imageBytes}></img>
                                </div>
                            :<div/>}
                        </div>
                        :<div/>}
                    </div>
                
                {this.state.status === "loading"?<Spinner/>:<div/>}
                <div>
                    
                {this.state.items !== undefined && this.state.items !== null && this.state.items.length > 0?this.state.items.map((l,i)=>{
                    return  <div className="thumbnail" key={l.TaskId}>
                                {l.ThumbnailUrl === undefined || l.ThumbnailUrl === null? 
                                    <img className='img' src={DefaultThumbnail} alt="Generating thumbnail" onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}></img>
                                    :<img className='img' src={l.ThumbnailUrl} alt={l.FileName} onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}></img>
                                }
                                <div className="play" onClick={({ detail }) => {this.handleVideoClick(l.TaskId, true);}}>
                                    <PlayButton/>
                                </div>
                                <div className="title" onClick={({ detail }) => {this.handleVideoClick(l.TaskId, false);}}>{l.FileName}</div>
                                <div className='status'>{l.Status}</div>
                                <div className="timestamp">{new Date(l.RequestTs).toLocaleString()}</div>
                                {l.Violation !== undefined && l.Violation !== null?
                                <div className='violation'>
                                {l.Violation?
                                <Badge color="red">Non-compliant</Badge>:
                                <Badge color="green">Compliant</Badge>}
                                </div>
                                :<div/>}
                                {this.props.readonlyMode? <div/>:
                                <div className='action'onClick={(e) => {
                                    this.setState({
                                        showDeleteConfirmModal: true,
                                        selectedItemId: l.TaskId
                                    })}}>
                                <Icon name="remove" visible={!this.props.readonlyMode} /></div>}
                                {l.Frames !== undefined && l.Frames !== null && l.Frames.length > 0?
                                <div>
                                    {
                                        this.state.showFrame.includes(l.TaskId)?
                                        <div>
                                            <Button iconName="treeview-collapse" variant="icon" onClick={()=>this.setState({showFrame: []})}></Button>
                                            {l.Frames.length} frames
                                            <div class="frames">
                                                <div className='close'>
                                                    <Button iconName="close" variant="icon" onClick={()=>this.setState({showFrame: []})}></Button>
                                                </div>                                            
                                                {l.Frames.map((item,idx)=> {
                                                    return <div className='box'>

                                                            <img src={item.image_uri}></img>
                                                            <div className="item">
                                                                <div className="key">Timestamp:</div>
                                                                {item.timestamp}
                                                            </div>
                                                            <div className="item">
                                                                <div className="key">Score:</div>
                                                                {item.score}
                                                            </div>
                                                            <div className="item">
                                                                <div className="key">Embedding Tex:</div>
                                                                {item.embedding_text}
                                                            </div>
                                                        </div>
                                                })}    
                                            </div>                                    
                                        </div>
                                        :<div>
                                            <Button iconName="treeview-expand" variant="icon" onClick={()=>this.setState({showFrame: [l.TaskId]})}></Button>
                                            {l.Frames.length} frames
                                        </div>
                                    }
                                </div>
                                :<div/>}
                            </div>
                             
                }): 
                this.state.items.length === 0 && this.state.status === null? <div className="noresult">No video found</div>
                :<div/>
                }

                <Modal
                    onDismiss={() => this.setState({showDeleteConfirmModal: false})}
                    visible={this.state.showDeleteConfirmModal}
                    header="Delete the video"
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
                    Are you sure you want to delete the video and analysis reports?
                </Modal>
                </div>
                <div className="showmore">
                    <Button 
                        loading={this.state.status === "loading"}
                        onClick={() => {
                            this.setState({pageSize: this.state.pageSize + this.showMoreNumber});
                            this.searchTimer = setTimeout(() => {
                                this.populateItems();
                              }, 500); 
                    }}>Show more</Button>
                </div>
            </div>
        );
    }
}

export default VideoSearch;