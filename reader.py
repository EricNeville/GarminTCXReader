import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import re
import datetime

activity_types = ['run']

lap_fields_dict = {
    'StartTime': str, 
    'TotalTimeSeconds': float, 
    'DistanceMeters': float, 
    'MaximumSpeed': float, 
    'Calories': int, 
    'AverageHeartRateBpm': int, 
    'MaximumHeartRateBpm': int, 
    'Intensity': str, 
    'TriggerMethod': str, 
    'AvgSpeed': float, 
    'AvgRunCadence': int, 
    'MaxRunCadence': int,
    'AvgWatts':int,
    'MaxWatts':int
}

trackpoint_fields_dict = {
    'Time':str, 
    'DistanceMeters': float, 
    'HeartRateBpm': int, 
    'Speed': float,
    'RunCadence':int,
    'LatitudeDegrees':float,
    'LongitudeDegrees':float,
    'AltitudeMeters':float,
    'Watts':int
}

class TCXReader:
    def __init__(self, file_path, activity_type):
        self.file_path = self.validate_path(file_path)
        self.activity_type = self.validate_type(activity_type)
        self.lap_df = self.get_lap_df()
        self.trackpoint_df = self.get_trackpoint_df()
    
    @staticmethod
    def validate_type(activity_type):
        if type(activity_type) == str:
            if activity_type.lower() in activity_types:
                return activity_type.lower()
        raise ValueError(f'Activity type must be one of {activity_types}')
        
    @staticmethod
    def validate_path(path):
        if isinstance(path, str):
            path = Path(path)
        if isinstance(path, Path):
            if path.exists():
                return path
            else:
                raise IOError(f'Path does not exist: {path}')
        else:
            raise ValueError(f'Invalid type for path argument: {type(path)}')
                
    @staticmethod
    def get_field_from_string(string, field, field_type):      
        try:
            if field == 'StartTime':
                val = re.findall('StartTime="(.*)Z"', string)[0]
            else:
                val = re.split(f'</?(?:ns3:)?{field}>', re.sub('<Value>|</Value>|\n|\s', '', ''.join(string)))[1]
            return field_type(val)
        except:
            print(f'Field {field} not found in string {string}')
            value = np.nan
            
            
    def get_lap_df(self):
        with open(self.file_path) as f:
            lines = f.readlines()
        laps = []
        in_lap = False
        in_track = False
        for i,line in enumerate(lines):
            if '<Lap' in line:
                in_lap = True
                lap_lines = []
            if in_lap:
                if '</Lap>' in line:
                    in_lap = False
                    laps.append(lap_lines)
                    continue
                if '<Track>' in line:
                    in_track = True
                if in_track:
                    if '</Track>' in line:
                        in_track = False
                        continue
                else:
                    lap_lines.append(line)
                    
        lap_data = []
        for lp in laps:
            lp_dict = {}
            lp_string = ''.join(lp)
            for field in lap_fields_dict.keys():
                value = self.get_field_from_string(lp_string, field, lap_fields_dict[field])
                lp_dict[field]=value
            lap_data.append(lp_dict)
        lap_df = pd.DataFrame(lap_data)
        lap_df.AvgRunCadence *=2
        lap_df.MaxRunCadence *=2
        lap_df['Pace'] = (1000/(lap_df.AvgSpeed))/60
        lap_df['StrideLength'] = (1000/lap_df.Pace)*(1/lap_df.AvgRunCadence)
        return lap_df
    
    def get_trackpoint_df(self):
        with open(self.file_path) as f:
            lines = f.readlines()
        trackpoints = []
        in_trackpoint = False
        for i,line in enumerate(lines):
            if '<Trackpoint' in line:
                in_trackpoint = True
                trackpoint_lines = []
            if in_trackpoint:
                trackpoint_lines.append(line)
                if '</Trackpoint>' in line:
                    trackpoints.append(trackpoint_lines)
                    in_trackpoint = False
                    
        trackpoint_data = []
        for tp in trackpoints:
            tp_dict = {}
            tp_string = ''.join(tp)
            for field in trackpoint_fields_dict.keys():
                value = self.get_field_from_string(tp_string, field, trackpoint_fields_dict[field])
                tp_dict[field]=value
            trackpoint_data.append(tp_dict)
        trackpoint_df = pd.DataFrame(trackpoint_data)
        trackpoint_df.RunCadence *=2
        trackpoint_df['Pace'] = (1000/(trackpoint_df.Speed))/60
        trackpoint_df['StrideLength'] = (1000/trackpoint_df.Pace)*(1/trackpoint_df.RunCadence)
        return trackpoint_df

    @staticmethod    
    def get_lap_data_from_trackpoint(lap_starts, lap_calories, tp_df):
        df = tp_df.copy()
        df['lap'] = np.array(lap_starts).searchsorted(df.Time)
        df.loc[0,'lap'] = 1
        df['DistanceDiff'] = df.DistanceMeters.diff()
        df.loc[0, 'DistanceDiff'] = df.loc[0, 'DistanceMeters']
        df = df.groupby('lap').agg(StartTime = ('Time','first'),
                                   DistanceMeters = ('DistanceDiff', 'sum'),
                                   MaximumSpeed = ('Speed', 'max'),
                                   AverageHeartRateBpm = ('HeartRateBpm', 'mean'),
                                   MaximumHeartRateBpm = ('HeartRateBpm', 'max'),
                                   AvgSpeed = ('Speed', 'mean'),
                                   AvgRunCadence = ('RunCadence', 'mean'),
                                   MaxRunCadence = ('RunCadence', 'max'),
                                   AvgWatts = ('Watts', 'mean'),
                                   MaxWatts = ('Watts', 'max'))
        df['TotalTimeSeconds'] = pd.to_datetime(df['StartTime']).diff().shift(-1).dt.total_seconds()
        df.loc[df.index[-1], 'TotalTimeSeconds'] = (pd.to_datetime(tp_df.Time.iloc[-1])-pd.to_datetime(df.loc[df.index[-1], 'StartTime'])).total_seconds()
        if len(df) == len(lap_calories):
            df['Calories'] = lap_calories
        else:
            raise ValueError(f'Length mismatch between lap_df and lap_calories: {len(df)} vs {len(lap_calories)}')
        df['Intensity'] = 'Active'
        df['TriggerMethod'] = 'Manual'
        df = df[['StartTime', 'TotalTimeSeconds', 'DistanceMeters', 'MaximumSpeed',
           'Calories', 'AverageHeartRateBpm', 'MaximumHeartRateBpm', 'Intensity',
           'TriggerMethod', 'AvgSpeed', 'AvgRunCadence', 'MaxRunCadence', 'AvgWatts', 'MaxWatts']]
        df[['AverageHeartRateBpm','AvgRunCadence']] = df[['AverageHeartRateBpm','AvgRunCadence']].astype(int)
        return df.reset_index(drop = True)