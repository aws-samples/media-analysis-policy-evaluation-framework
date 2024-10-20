import React from 'react';
import './videoScenes.css'
import { FetchPost } from "../resources/data-provider";
import { Pagination, Spinner, ExpandableSection } from '@cloudscape-design/components';
import { DecimalToTimestamp } from "../resources/utility";

class VideoScenes extends React.Component {

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
        
          FetchPost("/extraction/video/get-task-scenes", {
              "PageSize": this.state.pageSize,
              "FromIndex": (fromIndex - 1) * this.state.pageSize,
              "TaskId": this.props.item.Request.TaskId,
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
                                  items: resp.Scenes,
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
            <div className="videoscenes">
                {this.state.items && <div className='total'>{this.state.totalItems} scenes detected</div>}
                <div className='pager'>
                <Pagination
                    currentPageIndex={this.state.currentPageIndex}
                    onChange={({ detail }) => {
                            this.setState({currentPageIndex: detail.currentPageIndex, items:null});
                            this.populateItems(detail.currentPageIndex);
                        }
                    }
                    pagesCount={parseInt(this.state.totalItems/this.state.pageSize) + 1}
                    disabled={this.state.items === undefined || this.state.items === null || this.state.items.length === 0}
                    />
                </div>
                <div className='scenes'>
                {this.state.items !== undefined && this.state.items !== null?this.state.items.map((sc,i)=>{
                    return <ExpandableSection expanded headerText={`Scene${sc.Index} (${sc.Duration}s) [${DecimalToTimestamp(sc.StartTs)} - ${DecimalToTimestamp(sc.EndTs)}]`}>
                        <div className='scene'>
                            <div className='summary'>{sc.Summary}</div>
                            <b>{sc.Shots.length} shots</b><br/>
                            {sc.Shots.map((sh,j) => {
                                return sh.Frames.map((f,k) => {
                                    return <div className='frame' onClick={()=>this.handleFrameClick(f.Timestamp)}>
                                        <div className='ts'>{DecimalToTimestamp(f.Timestamp)}</div>
                                        <img src={f.S3Url} alt={`frame_${f.Timestamp}`}></img>
                                        <div className='label'>Shot{sh.Index}</div>
                                    </div>
                                    }
                                )
                            })}
                        </div>
                    </ExpandableSection>
                }):<div/>}
                </div>
                {this.state.status === "loading"?<Spinner/>:<div/>}
            </div>
        );
    }
}

export default VideoScenes;