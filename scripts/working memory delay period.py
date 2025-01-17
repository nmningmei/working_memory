# -*- coding: utf-8 -*-
"""
Created on Mon Nov 13 12:24:24 2017

@author: ning
"""

import os
import mne
from matplotlib import pyplot as plt
import numpy as np
import re
import pandas as pd
from mne.decoding import LinearModel,Vectorizer,SlidingEstimator,get_coef,cross_val_multiscore,GeneralizingEstimator
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.model_selection import KFold
"""Below are a few helper functions I no longer use"""
def exclude_rows(x):
    if re.compile('stimulus', re.IGNORECASE).search(x):
        return False
    else:
        return True
def choose_one_event(x,key = 'delay'):
    if re.compile(key,re.IGNORECASE).search(x):
        return True
    else:
        return False
def delay_onset(x,key='71'):
    if re.compile(key,re.IGNORECASE).search(x):
        return True
    else:
        return False
# I use this function
def make_clf():
    """
    Takes no argument, and return a pipeline of linear classifier, containing a scaler and a linear estimator
    """
    clf = []
    #clf.append(('vectorizer',Vectorizer()))
    clf.append(('scaler',StandardScaler()))
    estimator = SVC(kernel='linear',max_iter=int(-1),random_state=12345,class_weight='balanced')
    estimator = LinearModel(estimator) # extra step for decoding patterns
    clf.append(('estimator',estimator))
    clf = Pipeline(clf)
    return clf    
os.chdir('D:\\working_memory\\')
subs = np.arange(11,33)
subs = np.setdiff1d(subs,np.array([24,27])) # take out subject 24 and 27


from tqdm import tqdm
from sklearn import metrics
import pickle
n_ = 50 # 50 ms window/step
for sub in subs:    
    epoch_fif = [f for f in os.listdir() if ('-epo.fif' in f) and ('suj%d_'%(sub) in f)]  # list of two epochs  
    epochs_1 = mne.read_epochs(epoch_fif[0])
    epochs_2 = mne.read_epochs(epoch_fif[1])
    epochs = mne.concatenate_epochs([epochs_1,epochs_2]) # concatenate two epochs
    epochs.event_id = {'load_2':2,'load_5':5}# make sure the code name of the events are correct
    epochs.pick_types(eeg=True,eog=False) # take out eog channels
    
    labels = np.array(epochs.events[:,-1] == 2,dtype=int) # load 2 is positive
    data = epochs.get_data()
    times = epochs.times
    info = epochs.info
    times = times * info['sfreq'] # convert time from second to ms
    ch_names = epochs.ch_names
    del epochs
    
    cv = KFold(n_splits=4,shuffle=True,random_state=12345)# 4 folds cross validation
    # an algorithm to make position indeces for each segment of the decoding
    # in short, we should have 123 segments for a 6000 ms long epochs, using a 50 ms window
    size = len(times[::n_])
    scores=np.zeros((size,size,4))
    position_index = np.arange(times[0],times[-1],n_) + (n_ * 2)
    position_index = position_index.astype(int)
    clfs = []
    # train and test at the same time
    print('cv diagonal\n')
    for ii,idx_train in tqdm(enumerate(position_index),desc='diag loop'):
        scores_ = []
        clfs_ = []
        for train_,test_ in cv.split(data):
            clf = make_clf() # always make a new, untrained classifier before training
            clf.fit(data[train_,:,idx_train],labels[train_])
            clfs_.append(clf) # save the classifier at each time
            scores_.append(metrics.roc_auc_score(labels[test_],
                                    clf.predict(data[test_,:,idx_train])))
        scores[ii,ii,:] = scores_
        clfs.append(clfs_)
    
    print('cv different time samples\n')
    # train the classifier at time A and test the trained classifier at time B
    for ii,idx_train in tqdm(enumerate(position_index),desc='off diag loop'):
        for kk,idx_test in enumerate(position_index):
            if idx_train != idx_test:
                scores_ = []
                for jj,(train_,test_) in enumerate(cv.split(data)):
                    clf = clfs[ii][jj]
                    
                    scores_.append(metrics.roc_auc_score(labels[test_],
                                            clf.predict(data[test_,:,idx_test])))
                    
                scores[ii,kk,:] = scores_
    pickle.dump(scores,open('D:\\working_memory\\subject%d_timeSampling.p'%sub,'wb'))
    plt.close('all')
    """
    Figure 1: time generalization plot. 
    
    A grid of training and testing time. The color indicates the decoding score.
    A high score means the trained model (wherever it was trained) can predict load 2 and load 5 labels using just the signals
    In other words, the signals might similar to the where the model was trained.
    """
    fig, ax = plt.subplots(figsize=(12,10))
    im = ax.imshow(scores.mean(-1),interpolation=None,origin='lower',
                  cmap='winter',vmin=0.5,vmax=.8,extent=[-100,6000,-100,6000])
    ax.set(xlabel='Testing Time (ms)',ylabel='Training Time (ms)',
          title='Temporal Generalization: subject %d, load2 vs load5'%sub)
    
    ax.axvline(0,color='k')
    ax.axhline(0,color='k')
    cbar=plt.colorbar(im,ax=ax)
    cbar.ax.set_title('ROC AUC scores')
    fig.savefig('D:\\working_memory\\working_memory\\results\\sampled_time\\subject_%d_load2load5_generalization_scores.png'%sub,dpi=300)

    """
    Figure 2: time decoding scores
    
    Train and test at the same time.
    Higher score means the linear classifier is able to distinguish load 2 and load 5 using only the signals.
    """
    scores_mean = np.mean(scores.diagonal(),axis=0)
    scores_std = np.std(scores.diagonal(),axis=0)
    plt.close('all')
    fig,ax = plt.subplots(figsize=(20,6))
    time_picks = times[::50]
    scores_picks = scores_mean
    scores_se = (scores_std/2)
    ax.plot(time_picks,scores_picks,label='scores')
    ax.fill_between(time_picks,scores_picks-scores_se,scores_picks+scores_se,color='red',alpha=0.5)
    ax.axhline(0.5,color='k',linestyle='--',label='chance')
    ax.axvline(0,color='k',linestyle='--')
    ax.set(xlabel='Time (ms)',ylabel='ROC AUC',xlim=(-100,6000),ylim=(0.35,1.),title='subject_%d_load2load5_decoding_scores'%sub)
    ax.set(xticks=np.arange(-100,6000,400))
    ax.legend()
    fig.savefig('working_memory\\results/sampled_time/subject_%d_load2load5_decoding_scores.png'%sub,dpi=300)

    
    coef = []
    for clfs_ in clfs:
        coef_ = [get_coef(clf,'patterns_',inverse_transform=True) for clf in clfs_]
        coef.append(coef_)
    coef = np.array(coef)
    evoked = mne.EvokedArray(np.mean(coef,axis=1).T,info,tmin=times[0])
    evoked.times = times[::n_]
    evoked.save('sample_time/subject_%d_load2load5_patterns-evo.fif'%sub,)
    del evoked
import matplotlib
font = {'weight':'bold',
        'size':16}
matplotlib.rc('font',**font)
os.chdir('D:\\working_memory\\')
subs = np.arange(11,33)
subs = np.setdiff1d(subs,np.array([24,27]))
save_dir = 'D:\\working_memory\\working_memory\\results\\'
for sub in subs:
    evoked = mne.read_evokeds('sample_time/subject_%d_load2load5_patterns-evo.fif'%sub,)
    evoked = evoked[0]
    evoked.times = np.arange(-100,6001,50)
    """
    Figure 3: decoding patterns
    
    Train and test at the same time.
    Higher flatuation means bigger difference in terms of amplitude between load 2 and load 5 at the given time.
    """
    plt.close('all')
    fig,ax = plt.subplots(figsize=(12,15))
    fig=mne.viz.plot_evoked_image(evoked,axes=ax)
    fig.axes[0].set(yticks=np.arange(len(evoked.ch_names)),yticklabels=evoked.ch_names)
    fig.savefig(save_dir+'sampled_time\\subject_%d_load2load5_difference_image.png'%sub,dpi=300)

    evoked.times = np.arange(-0.1,6.001,0.05)[:-1]
    a,b=-10,10
    fig = mne.viz.plot_evoked_joint(evoked,
                                    topomap_args={'scaling_time':1e3,'size':1,
                                                 'vmin':a,'vmax':b},)
    fig.savefig(save_dir+'sampled_time\\subject_%d_load2load5__difference_joint.png'%sub,dpi=300)



#for sub in subs:
#    files = [f for f in os.listdir() if ('suj%d_'%(sub) in f) and ('vhdr' in f)]
#    _,_,day_ = re.findall('\d+',files[0])
#    if os.path.exists('suj%d_wml2_day%s-epo.fif'%(sub,day_)):
#        preprocessing = False
#    else:
#        preprocessing = True
#    
#    if preprocessing:
#        for eeg in files:
#            _,load,day = re.findall('\d+',eeg)
#            montage = mne.channels.read_montage('standard_1020')
#            raw = mne.io.read_raw_brainvision(eeg,eog=('LOc','ROc'),preload=True)
#            raw.set_channel_types({'Aux1':'stim','STI 014':'stim'})
#            raw.set_montage(montage)
#            raw.pick_types(meg=False,eeg=True,eog=True,stim=False)
#            raw.set_eeg_reference()
#            raw.apply_proj()
#            picks = mne.pick_types(raw.info,meg=False,eeg=True,eog=False)
#            raw.filter(1,40,picks=picks,fir_design='firwin')    
#            raw.notch_filter(np.arange(60,241,60),fir_design='firwin')
#            noise_cov = mne.compute_raw_covariance(raw,n_jobs=4)
#            
#            events_file = 'suj%d_wml%s_day%s.evt'%(sub,load,day)
#            events = pd.read_csv(events_file,sep='\t')
#            events.columns = ['TMS','code','TriNo','Comnt']
#            row_idx = events['Comnt'].apply(exclude_rows)
#            events = events[row_idx]
#            event_rows = events['Comnt'].apply(choose_one_event)
#            events = events[event_rows]
#            events_delay_onset_rows = events['Comnt'].apply(delay_onset)
#            events = events[events_delay_onset_rows]
#            events['TMS'] = events['TMS'] / 1e3
#            event_id = {'load_%s'%(load):int(load)}
#            events = events[['TMS','code','TriNo']].values.astype(int)
#            events[:,-1] = int(load)
#            
#            reject = {'eeg':100e-6,'eog':300e-6}
#            epochs = mne.Epochs(raw,events,event_id,tmin=-0.1,tmax=6,proj=True,baseline=(-0.1,0),reject=None,detrend=1,preload=True)
#            ica = mne.preprocessing.ICA(n_components=.95,n_pca_components=.95,
#                                        noise_cov=noise_cov,random_state=12345,method='extended-infomax',max_iter=int(3e3),)
#            ica.fit(raw,reject=reject,decim=3)
#            ica.detect_artifacts(epochs,eog_ch=['LOc','ROc'])
#            epochs = ica.apply(epochs,exclude=ica.exclude,)
#            epochs.save(eeg[:-5]+'-epo.fif',)
#    
#for sub in subs:    
#    epoch_fif = [f for f in os.listdir() if ('-epo.fif' in f) and ('suj%d_'%(sub) in f)]    
#    epochs_1 = mne.read_epochs(epoch_fif[0])
#    epochs_2 = mne.read_epochs(epoch_fif[1])
#    epochs = mne.concatenate_epochs([epochs_1,epochs_2])
#    epochs.event_id = {'load_2':2,'load_5':5}
#    epochs.pick_types(eeg=True,eog=False)
#    
#    labels = np.array(epochs.events[:,-1] == 2,dtype=int)
#    data = epochs.get_data()
#    times = epochs.times
#    info = epochs.info
#    del epochs
#    #del raw
#    
#    
#    clf = []
#    #clf.append(('vectorizer',Vectorizer()))
#    clf.append(('scaler',StandardScaler()))
#    estimator = SVC(kernel='linear',max_iter=int(-1),random_state=12345,class_weight='balanced')
#    #estimator = LinearModel(estimator)
#    clf.append(('estimator',estimator))
#    clf = Pipeline(clf)
#    cv = KFold(n_splits=4,shuffle=True,random_state=12345)
#    
#    td = SlidingEstimator(clf,scoring='roc_auc',n_jobs=4)
#    scores = cross_val_multiscore(td,data,labels,cv=cv,)
#    scores_mean = np.mean(scores,axis=0)
#    scores_std = np.std(scores,axis=1)
#    plt.close('all')
#    fig,ax = plt.subplots(figsize=(20,6))
#    time_picks = times[::50]
#    scores_picks = scores_mean[::50]
#    scores_se = (scores_std/2)[::50]
#    ax.plot(time_picks,scores_picks,label='scores')
#    ax.fill_between(time_picks,scores_picks-scores_se,scores_picks+scores_se,color='red',alpha=0.5)
#    ax.axhline(0.5,color='k',linestyle='--',label='chance')
#    ax.axvline(0,color='k',linestyle='--')
#    ax.set(xlabel='Time (Sec)',ylabel='ROC AUC',xlim=(-0.1,6),ylim=(0.35,1.),title='subject_%d_load2load5_decoding_scores'%sub)
#    ax.legend()
#    fig.savefig('results/subject_%d_load2load5_decoding_scores.png'%sub,dpi=300)
#    plt.close('all')
#    
#    coef = []
#    clf = []
#    #clf.append(('vectorizer',Vectorizer()))
#    clf.append(('scaler',StandardScaler()))
#    estimator = SVC(kernel='linear',max_iter=int(-1),random_state=12345,class_weight='balanced')
#    estimator = LinearModel(estimator)
#    clf.append(('estimator',estimator))
#    clf = Pipeline(clf)
#    for train,test in cv.split(data):
#        td = SlidingEstimator(clf,scoring='roc_auc',n_jobs=4)
#        td.fit(data[train],labels[train])
#        coef_ = get_coef(td,'patterns_',inverse_transform=True)
#        coef.append(coef_)
#    evoked = mne.EvokedArray(np.mean(coef,axis=0),info,tmin=times[0])
#    evoked.save('subject_%d_load2load5_patterns-evo.fif'%sub,)
#    del evoked
#    #evoked.plot_joint(title='patterns')