import { useState, useRef } from "react";
import Header from "@cloudscape-design/components/header";
import * as React from "react";
import Alert from "@cloudscape-design/components/alert";
import {withAuthenticator} from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import {Navigation} from './components/commons/common-components';
import { AppLayout } from '@cloudscape-design/components';
import TopNavigation from "@cloudscape-design/components/top-navigation";
import { BreadcrumbGroup, Link, SpaceBetween } from '@cloudscape-design/components';
import VideoMain from './components/videoMain'
import Config from './components/config';

const ITEMS = [
  {
    type: "link",
    text: "Media files",
    id:"video",
    href:"#/video",
  },
  {
    type: "link",
    text: "Logout",
    id:"logout",
    href:"#/logout",
  }
]
/*const ITEMS = [
  {
    type: "link",
    text: "Media files",
    id:"video",
    href:"#/video",
  },
  {
    type: "link",
    text: "Configuration", 
    id:"config", 
    href:"#/config",
  },
  {
    type: "link",
    text: "API Document", 
    id:"apidoc", 
    href:process.env.REACT_APP_API_SWAGGER_URL,
    external: true
  }
]*/


const App = ({ signOut, user }) => {
  const [currentPage, setCurrentPage] = useState("video");
  const [navigationOpen, setNavigationOpen] = useState(true);
  const [activeNavHref, setActiveNavHref] = useState("#/video");
  const [displayTopMenu, setDisplayTopMenu] = useState(window.self == window.top);
  const [cleanSelectionSignal, setCleanSelectionSignal] = useState(null);

  const appLayout = useRef();

  const [selectedItems, setSelectedItems] = useState([]); 

  const handleNavigationChange = () => {
    setNavigationOpen(!navigationOpen);
  }

  const handleNavItemClick = e => {
    if (e.detail.id === "logout") {
      signOut();
      return;
    }
    setCurrentPage(e.detail.id);
    setCleanSelectionSignal(Math.random());

    setActiveNavHref("#/"+e.detail.id);
  }

  const handleTopClick = e => {
    setCurrentPage("video");
    setActiveNavHref("#/video")
    setNavigationOpen(true);
  }

    return (
      <div>{displayTopMenu?
      <TopNavigation      
        identity={{
          href: "#",
          title: "Content Analysis Using Custom Policy",
          onFollow: handleTopClick   
        }}
        utilities={[
          {
            type: "menu-dropdown",
            text: user.username,
            description: user.email,
            iconName: "user-profile",
            onItemClick: signOut,
            items: [
              { type: "button", id: "signout", text: "Sign out"}
            ]
          }
        ]}
        i18nStrings={{
          searchIconAriaLabel: "Search",
          searchDismissIconAriaLabel: "Close search",
          overflowMenuTriggerText: "More",
          overflowMenuTitleText: "All",
          overflowMenuBackIconAriaLabel: "Back",
          overflowMenuDismissIconAriaLabel: "Close menu"
        }}
      />:<div/>}
      <AppLayout
        headerSelector="#header"
        ref={appLayout}
        contentType="table"
        navigationOpen={navigationOpen}
        onNavigationChange={handleNavigationChange}
        navigation={
          <Navigation 
            onFollowHandler={handleNavItemClick}
            selectedItems={["video"]}
            activeHref={activeNavHref}
            items={ITEMS} 
          />}
        navigationWidth={180}
        toolsHide={true}
        content={
          currentPage === "video"?<VideoMain cleanSelectionSignal={cleanSelectionSignal} readOnlyUsers={process.env.REACT_APP_READONLY_USERS.toString().split(',')} />:
          currentPage === "config"?<Config />:
           <VideoMain onNavigate={e=>{setCurrentPage(e);}}/>
        }
      >
    </AppLayout>
    </div>
  );
}
export default withAuthenticator(App);
