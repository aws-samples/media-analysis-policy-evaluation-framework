import React, { Component } from 'react';
import { v4 as uuid4 } from 'uuid';

class ProgressBar extends Component {
    constructor(props) {
        super(props);
        this.state = {
            hoverTime: null
        };
        this.populTimer = null;
    }

    handleHover = (time) => {
        this.setState({ hoverTime: time });
    };

    handleLeave = () => {
        clearTimeout(this.populTimer);
        this.populTimer = setTimeout(() => {
            this.setState({ hoverTime: null });
        }, 1000); 
    };

    handleLabelClick = (label) => {
        // Handle label click action
        //alert('Label clicked:', label);
        this.props.OnLabelClick(label);
    };

    render() {
        const { duration, labels, labelType } = this.props;
        const { hoverTime } = this.state;

        return (
            <div style={{ position: 'relative' }}>
                <div
                    style={{
                        width: '100%',
                        height: '15px',
                        backgroundColor: '#DCDCDC',
                        position: 'relative',
                        cursor: 'pointer'
                    }}
                >
                    {labels.map((label) => (
                        <div
                            key={`${labelType}_w_${label.timestamp}`}
                            style={{
                                position: 'absolute',
                                left: `${(label.timestamp / duration) * 100}%`,
                                height: '15px',
                                width: '10px',
                                backgroundColor: 'black',
                                cursor: 'pointer',
                                zIndex: 100
                            }}
                            onClick={() => {this.handleLabelClick(label)}}
                            onMouseOver={() => this.handleHover(label.timestamp)}
                            onMouseOut={() => this.handleLeave(label.timestamp)}
                        ></div>
                    ))}
                    <div key={`${labelType}_c`}
                        style={{
                            position: 'absolute',
                            top: 0,
                            right: 0,
                            width: `${(hoverTime / duration) * 100}%`,
                            height: '100%',
                            //backgroundColor: 'green'
                        }}
                    />
                    {hoverTime && (
                        <div key={`${labelType}_y`}
                            style={{
                                position: 'absolute',
                                top: '-30px',
                                left: `${(hoverTime / duration) * 100}%`,
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                color: '#fff',
                                padding: '5px',
                                borderRadius: '5px'
                            }}
                        >
                            {this.formatTime(hoverTime)}
                        </div>
                    )}
                </div>
            </div>
        );
    }

    formatTime = (seconds) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainingSeconds = Math.floor(seconds % 60);

        const formattedTime = [
            hours.toString().padStart(2, '0'),
            minutes.toString().padStart(2, '0'),
            remainingSeconds.toString().padStart(2, '0')
        ].join(':');

        return formattedTime;
    }
}

export default ProgressBar;
