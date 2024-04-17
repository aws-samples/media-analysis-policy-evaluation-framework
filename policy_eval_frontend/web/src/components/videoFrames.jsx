import React from 'react';
import './videoFrames.css'
import { FetchPost } from "../resources/data-provider";
import { Pagination, Spinner } from '@cloudscape-design/components';
import { DecimalToTimestamp } from "../resources/utility";

class VideoFrames extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: null, // null, loading, loaded
            alert: null,
            pageSize: 10,
            currentPageIndex: 1,
            totalItems: 0,
            items: null
        };
        this.item = null;
    }

    componentDidMount() {
        if (this.props.item.Request.TaskId !== null) {
          this.populateItems();    
        }
    }

    populateItems(fromIndex=null) {
        this.setState({status: "loading"});
        if (fromIndex === null)
            fromIndex = this.state.currentPageIndex
        
          FetchPost("/extraction/video/get-task-frames", {
              "PageSize": this.state.pageSize,
              "FromIndex": (fromIndex - 1) * this.state.pageSize,
              "TaskId": this.props.item.Request.TaskId
          }).then((data) => {
                  var resp = data.body;
                  if (data.statusCode !== 200) {
                      this.setState( {status: null, alert: data.body});
                  }
                  else {
                      if (resp !== null) {
                          //console.log(items);
                          this.setState(
                              {
                                  items: resp.Frames,
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

    handleFrameClick(timestamp) {
        //alert(timestamp);
        this.props.OnFrameClick(timestamp);
    }
    render() {
        return (
            <div className="videoframes">
                <div className='pager'>
                <Pagination
                    currentPageIndex={this.state.currentPageIndex}
                    onChange={({ detail }) => {
                            this.setState({currentPageIndex: detail.currentPageIndex, items:null});
                            this.populateItems(detail.currentPageIndex);
                        }
                    }
                    pagesCount={parseInt(this.state.totalItems/this.state.pageSize)}
                    disabled={this.state.items === undefined || this.state.items === null || this.state.items.length === 0}
                    />
                </div>
                <div className='frames'>
                {this.state.items !== undefined && this.state.items !== null?this.state.items.map((l,i)=>{
                    return <div className='frame' onClick={()=>this.handleFrameClick(l.Timestamp)}>
                        <div className='ts'>{DecimalToTimestamp(l.Timestamp)}</div>
                        <img src={l.S3Url} alt={`image_${i}`}></img>
                        {l.ImageCaption && <div className='caption'><b>Summary:</b> {l.ImageCaption}</div>}
                        {l.Label && <div className='label'><b>Labels:</b> {l.Label.join(', ')}</div>}
                        {l.Moderation && <div className='label'><b>Moderation Labels:</b> {l.Moderation.join(', ')}</div>}
                        {l.Celebritie && <div className='label'><b>Celebrities:</b> {l.Celebritie.join(', ')}</div>}
                        {l.Text && <div className='label'><b>Text:</b> {l.Text.join(', ')}</div>}
                    </div>
                }):<div/>}
                </div>
                {this.state.status === "loading"?<Spinner/>:<div/>}
            </div>
        );
    }
}

export default VideoFrames;