import React from 'react';
import './videoMain.css'
import { Button, Modal, Icon } from '@cloudscape-design/components';
import VideoSearch from './videoSearch'
import VideoDetail from './videoDetail'
import { getCurrentUser } from 'aws-amplify/auth';
import VideoUpload from './videoUpload';

class VideoMain extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: "loading", // null, loading, loaded
            alert: null,
            items: null,
            filterText: null,
            selectedItemId: null,
            currentUserName: null,
            refreshSearchTaskId: false,

            showUploadModal: false
        };
    }
    async componentDidMount() {
        if (this.state.currentUserName === null) {
            const { username } = await getCurrentUser();
            this.setState({currentUserName: username});
        }
    }

    componentDidUpdate(prevProps) {
        if (prevProps.cleanSelectionSignal !== this.props.cleanSelectionSignal) {
            this.setState({selectedItemId: null})
        }
      }

    handleThumbnailClick = (taskId, autoPlay=false) => {
        this.setState({selectedItemId: taskId, autoPlay: autoPlay});
    }

    handleVideoUpload = () => {
        this.setState({showUploadModal: false, refreshSearchTaskId: Math.random().toString()});
    }

    render() {
        return (
            <div className="videomain">
                {this.state.selectedItemId === null?
                <div>
                    <div className='globalaction'>
                        {!this.props.readOnlyUsers.includes(this.state.currentUserName)?
                        <div className='upload'><Button onClick={()=>this.setState({showUploadModal: true})} variant="primary">
                            <Icon name="upload" />&nbsp;
                            Upload a video
                        </Button></div>
                        :<div className='readonly-note'>Upload is currently disabled for this user</div>}
                        <div/>
                    </div>
                    <VideoSearch 
                            onThumbnailClick={this.handleThumbnailClick} 
                            currentUserName={this.state.currentUserName}
                            readonlyMode={this.props.readOnlyUsers.includes(this.state.currentUserName)}
                            refreshSearchTaskId={this.state.refreshSearchTaskId}
                            />
                </div>
                :<VideoDetail 
                    taskId={this.state.selectedItemId} 
                    autoPlay={this.state.autoPlay}
                    onClose={(detail)=> this.setState({selectedItemId: null})}
                >
                </VideoDetail>
                }
                <Modal
                    onDismiss={() => this.setState({showUploadModal: false})}
                    visible={this.state.showUploadModal}
                    size='max'
                >
                    <VideoUpload onSubmit={this.handleVideoUpload} onCancel={()=>this.setState({showUploadModal: false})}/>
                </Modal>

            </div>
        );
    }
}

export default VideoMain;