import React, { Component } from "react";
import Avatar from "./Avatar";
import "./Messages.css";

class UserMessageBox extends Component {
  constructor(props) {
    super(props);
  }
  render() {
    return (
      <li className={`message ${this.props.appearance} appeared`}>
        <Avatar></Avatar>
        <div className="text_wrapper">
          <div className="text">{this.props.message}</div>
        </div>
      </li>
    );
  }
}

export default UserMessageBox;
