import React from 'react';
import './config.css'
import { Button, TextContent } from '@cloudscape-design/components';

class Config extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: "loading", // null, loading, loaded
            alert: null,
            selectedItems: [],
            pageItems: [],
            items: null,
            currentPageIndex: 1,
            isDescending: false,
            filterText: null,

            showWarningModal: false,
            stopStreamStatus: null
        };

        this.PAGE_SIZE = 10;
        this.TASK_LIMIT = 50;

    }


    render() {
        return (
            <div className="config">
                
            </div>
        );
    }
}

export default Config;